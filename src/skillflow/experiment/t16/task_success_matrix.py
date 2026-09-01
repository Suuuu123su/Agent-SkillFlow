"""v3 Task Success bridge/calibration Smoke Matrix 的机械展开。"""

from pathlib import Path
from typing import Annotated, Literal, Self

import yaml
from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from skillflow.experiment.t16.budget import BudgetConfig
from skillflow.experiment.t16.provider import ProviderConfig
from skillflow.experiment.t16.task_success_prereg_models import (
    TaskSuccessPreregistrationV3,
)
from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.matrix_design import HiaaCell
from skillflow.models.references import EffectSelectorRef, ScenarioPath

PositiveInt = Annotated[int, Field(ge=1)]


class TaskSuccessSmokeTrial(StrictModel):
    """一条尚未执行的 v3 Smoke 链。"""

    trial_id: NonEmptyStr
    scenario: ScenarioPath
    condition_id: NonEmptyStr
    semantic_instance_id: NonEmptyStr
    pair_id: NonEmptyStr
    repeat_index: PositiveInt
    task_prompt: NonEmptyStr
    prompt_contract_id: NonEmptyStr
    artifact_schema_id: NonEmptyStr
    task_success_spec_id: NonEmptyStr
    task_output_contract_id: NonEmptyStr
    target_effect_selectors: Annotated[tuple[EffectSelectorRef, ...], Field(min_length=1)]
    observation_sessions: tuple[int, ...]
    hiaa_cell: HiaaCell | None = None
    harm_selector: EffectSelectorRef | None = None


class TaskSuccessSmokeMatrix(StrictModel):
    """48 条、默认禁止 live 的 v3 Matrix。"""

    schema_version: Literal["0.3"] = "0.3"
    id: NonEmptyStr
    study_role: Literal["bridge_calibration"] = "bridge_calibration"
    preregistration_id: NonEmptyStr
    simulation_only_until_authorized: Literal[True] = True
    provider: ProviderConfig
    budget: BudgetConfig
    trials: Annotated[tuple[TaskSuccessSmokeTrial, ...], Field(min_length=48, max_length=48)]

    @model_validator(mode="after")
    def require_unique_locked_trials(self) -> Self:
        """拒绝重复 Trial，并保持 live 默认关闭。"""
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
            raise PydanticCustomError(
                "t16_task_success_matrix_duplicate",
                "v3 Matrix Trial 不得重复",
            )
        if self.budget.allow_live:
            raise PydanticCustomError(
                "t16_task_success_matrix_live_enabled",
                "v3 Smoke Matrix 默认不得启用 live",
            )
        return self


class TaskSuccessMatrixDriftError(ValueError):
    """静态 v3 Matrix 与机械展开不一致。"""

    __slots__ = ("matrix_id", "preregistration_id")

    def __init__(self, matrix_id: str, preregistration_id: str) -> None:
        """保存两个发生漂移的版本化身份。"""
        super().__init__(matrix_id, preregistration_id)
        self.matrix_id = matrix_id
        self.preregistration_id = preregistration_id

    def __str__(self) -> str:
        """返回不含任务正文的稳定诊断。"""
        return f"{self.matrix_id} 与 {self.preregistration_id} 的 v3 机械展开不一致"


def build_task_success_smoke_matrix(
    registration: TaskSuccessPreregistrationV3,
) -> TaskSuccessSmokeMatrix:
    """按冻结条件、两个实例和两个 repeat 机械生成 48 条链。"""
    instance_sets = {item.instance_set_id: item for item in registration.instance_sets}
    trials: list[TaskSuccessSmokeTrial] = []
    for condition in registration.conditions:
        for template in instance_sets[condition.instance_set_id].templates:
            instance_id = f"{condition.instance_set_id}-{template.template_id}"
            pair_id = f"{condition.pair_group_id}-{template.template_id}"
            prompt = f"{template.task_prompt}\n{registration.prompt_contract.instruction}"
            trials.extend(
                TaskSuccessSmokeTrial(
                    trial_id=(
                        f"task-success-smoke-{condition.condition_id}-"
                        f"{template.template_id}-r{repeat_index}"
                    ),
                    scenario=condition.scenario,
                    condition_id=condition.condition_id,
                    semantic_instance_id=instance_id,
                    pair_id=pair_id,
                    repeat_index=repeat_index,
                    task_prompt=prompt,
                    prompt_contract_id=registration.prompt_contract.id,
                    artifact_schema_id=(registration.prompt_contract.structured_result_schema_id),
                    task_success_spec_id=condition.task_success_spec_id,
                    task_output_contract_id=condition.task_output_contract_id,
                    target_effect_selectors=condition.target_effect_selectors,
                    observation_sessions=condition.observation_sessions,
                    hiaa_cell=condition.hiaa_cell,
                    harm_selector=condition.harm_selector,
                )
                for repeat_index in range(1, registration.repeats_per_instance + 1)
            )
    return TaskSuccessSmokeMatrix(
        id="t16-task-success-smoke-v3",
        preregistration_id=registration.id,
        provider=registration.provider,
        budget=registration.budget,
        trials=tuple(trials),
    )


def write_task_success_smoke_matrix(
    path: Path,
    matrix: TaskSuccessSmokeMatrix,
) -> None:
    """以稳定字段顺序写出机械生成的 v3 Matrix。"""
    content = yaml.safe_dump(
        matrix.model_dump(mode="json"),
        allow_unicode=True,
        sort_keys=False,
    )
    path.write_text(content, encoding="utf-8")
