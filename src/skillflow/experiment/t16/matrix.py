"""T16 预注册到 48/360/第二模型抽样矩阵的机械展开。"""

from dataclasses import dataclass
from enum import StrEnum, unique
from pathlib import Path
from typing import Annotated, Literal, Self, assert_never

import yaml
from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from skillflow.experiment.t16.preregistration_models import (
    SemanticInstanceSet,
    SemanticTemplate,
    T16Preregistration,
)
from skillflow.experiment.t16.provider import ProviderConfig
from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.references import ScenarioPath
from skillflow.validation import validate_yaml_document

PositiveInt = Annotated[int, Field(ge=1)]


@unique
class MatrixKind(StrEnum):
    """T16-A 固定交付的三类 Matrix。"""

    SMOKE = "smoke"
    MODEL1 = "model1"
    MODEL2_SUBSET = "model2_subset"


class TrialSpec(StrictModel):
    """一条实验链的稳定身份与输入。"""

    trial_id: NonEmptyStr
    scenario: ScenarioPath
    condition_id: NonEmptyStr
    semantic_instance_id: NonEmptyStr
    pair_id: NonEmptyStr
    repeat_index: PositiveInt
    task_prompt: NonEmptyStr


class T16Matrix(StrictModel):
    """一个 Provider 上可逐链执行的确定性矩阵。"""

    schema_version: Literal["0.1"] = "0.1"
    id: NonEmptyStr
    preregistration_id: NonEmptyStr
    kind: MatrixKind
    provider: ProviderConfig
    trials: Annotated[tuple[TrialSpec, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def reject_duplicate_trials(self) -> Self:
        """Trial ID 与四元身份都必须唯一。"""
        trial_ids = tuple(item.trial_id for item in self.trials)
        identities = tuple(
            (
                item.condition_id,
                item.semantic_instance_id,
                item.pair_id,
                item.repeat_index,
            )
            for item in self.trials
        )
        if len(set(trial_ids)) != len(trial_ids) or len(set(identities)) != len(identities):
            raise PydanticCustomError("t16_matrix_trial_duplicate", "Matrix Trial 不能重复")
        return self


@dataclass(frozen=True, slots=True)
class MatrixDriftError(ValueError):
    """静态 Matrix 与预注册机械展开不一致。"""

    matrix_id: str
    preregistration_id: str

    def __str__(self) -> str:
        """返回稳定诊断。"""
        return f"{self.matrix_id} 与 {self.preregistration_id} 的机械展开不一致"


def build_matrix(
    registration: T16Preregistration,
    kind: MatrixKind,
    provider: ProviderConfig,
) -> T16Matrix:
    """严格按预注册展开矩阵。"""
    instance_sets = {item.instance_set_id: item for item in registration.instance_sets}
    trials: list[TrialSpec] = []
    repeat_count = _repeat_count(kind, registration)
    for condition in registration.conditions:
        instance_set = instance_sets[condition.instance_set_id]
        for template in _selected_templates(kind, instance_set, registration):
            pair_id = f"{condition.pair_group_id}-{template.template_id}"
            instance_id = f"{instance_set.instance_set_id}-{template.template_id}"
            trials.extend(
                TrialSpec(
                    trial_id=(
                        f"{kind.value}-{condition.condition_id}-"
                        f"{template.template_id}-r{repeat_index}"
                    ),
                    scenario=condition.scenario,
                    condition_id=condition.condition_id,
                    semantic_instance_id=instance_id,
                    pair_id=pair_id,
                    repeat_index=repeat_index,
                    task_prompt=template.task_prompt,
                )
                for repeat_index in range(1, repeat_count + 1)
            )
    return T16Matrix(
        id=f"t16-{kind.value}",
        preregistration_id=registration.id,
        kind=kind,
        provider=provider,
        trials=tuple(trials),
    )


def load_matrix(path: Path) -> T16Matrix:
    """读取一个严格 T16 Matrix YAML。"""
    return validate_yaml_document(path, T16Matrix)


def validate_matrix_against_preregistration(
    matrix: T16Matrix,
    registration: T16Preregistration,
) -> None:
    """拒绝静态 Matrix 与机械展开结果之间的任何漂移。"""
    expected = build_matrix(registration, matrix.kind, matrix.provider)
    if matrix != expected:
        raise MatrixDriftError(matrix.id, registration.id)


def write_matrix(path: Path, matrix: T16Matrix) -> None:
    """确定性写出静态 Matrix YAML。"""
    content = yaml.safe_dump(
        matrix.model_dump(mode="json"),
        allow_unicode=True,
        sort_keys=False,
    )
    path.write_text(content, encoding="utf-8")


def _repeat_count(kind: MatrixKind, registration: T16Preregistration) -> int:
    match kind:
        case MatrixKind.SMOKE:
            return 2
        case MatrixKind.MODEL1 | MatrixKind.MODEL2_SUBSET:
            return registration.repeats_per_instance
        case unreachable:
            assert_never(unreachable)


def _selected_templates(
    kind: MatrixKind,
    instance_set: SemanticInstanceSet,
    registration: T16Preregistration,
) -> tuple[SemanticTemplate, ...]:
    match kind:
        case MatrixKind.SMOKE:
            return instance_set.templates[:2]
        case MatrixKind.MODEL1:
            return instance_set.templates
        case MatrixKind.MODEL2_SUBSET:
            selected = set(registration.model2_subset_template_ids)
            return tuple(item for item in instance_set.templates if item.template_id in selected)
        case unreachable:
            assert_never(unreachable)
