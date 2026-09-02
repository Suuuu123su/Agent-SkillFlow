"""T17-E/F/G 真实模型预注册与 Matrix 机械展开。"""

import json
from dataclasses import dataclass
from enum import StrEnum, unique
from pathlib import Path
from typing import Annotated, Literal, Self, assert_never

import yaml
from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from skillflow.experiment.t16.budget import BudgetConfig
from skillflow.experiment.t16.provider import ProviderConfig
from skillflow.experiment.t17.scenario_registry import (
    T17ScenarioMeasurementRegistry,
    T17VariantMeasurement,
    expand_variant_measurements,
)
from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.enums import EnforcementMode
from skillflow.models.matrix import ExperimentMatrix, ExperimentVariant
from skillflow.models.references import ArtifactAliasRef, ScenarioPath
from skillflow.models.scenario import Scenario
from skillflow.validation import validate_yaml_document

PositiveInt = Annotated[int, Field(ge=1)]
EXPECTED_DEFENSE_BASE_CONFIGS = 21
EXPECTED_DEFENSE_COMPLEMENTS = 18


@unique
class T17LiveStage(StrEnum):
    """预注册的真实模型执行阶段。"""

    CANARY = "canary"
    MODEL1 = "model1"
    MODEL2_CANARY = "model2_canary"
    MODEL2 = "model2"
    DEFENSE = "defense"


class T17SemanticTemplate(StrictModel):
    """保持任务含义不变的固定提示前缀。"""

    template_id: NonEmptyStr
    prefix: NonEmptyStr


class T17LivePreregistration(StrictModel):
    """T17-E/F/G 的模型、样本、统计和默认关闭预算。"""

    schema_version: Literal["0.1"] = "0.1"
    id: NonEmptyStr
    scenario_registry_id: NonEmptyStr
    semantic_templates: Annotated[
        tuple[T17SemanticTemplate, ...],
        Field(min_length=5, max_length=5),
    ]
    repeats_per_instance: Literal[3] = 3
    bootstrap_resamples: Literal[10_000] = 10_000
    bootstrap_seed: Literal[17_017] = 17_017
    model1_provider: ProviderConfig
    model2_provider: ProviderConfig
    model1_budget: BudgetConfig
    model2_budget: BudgetConfig
    model1_full_budget: BudgetConfig
    model2_full_budget: BudgetConfig
    defense_budget: BudgetConfig
    model1_prompt_cache_mode: Literal["explicit"] = "explicit"
    model2_prompt_cache_mode: Literal["automatic"] = "automatic"

    @model_validator(mode="after")
    def require_live_disabled_until_approval(self) -> Self:
        """静态预注册不得自行授权任何真实请求。"""
        budgets = (
            self.model1_budget,
            self.model2_budget,
            self.model1_full_budget,
            self.model2_full_budget,
            self.defense_budget,
        )
        if any(item.allow_live for item in budgets):
            raise PydanticCustomError(
                "t17_prereg_live_enabled",
                "T17 静态预注册必须保持 allow_live=false",
            )
        identifiers = tuple(item.template_id for item in self.semantic_templates)
        if len(set(identifiers)) != len(identifiers):
            raise PydanticCustomError(
                "t17_semantic_template_duplicate",
                "semantic template ID 不得重复",
            )
        return self


class T17LiveTrial(StrictModel):
    """一条尚未发送 API 请求的核心 Trial。"""

    trial_id: NonEmptyStr
    variant: NonEmptyStr
    source_variant: NonEmptyStr
    scenario: ScenarioPath
    scenario_id: NonEmptyStr
    semantic_instance_id: NonEmptyStr
    semantic_template_id: NonEmptyStr
    repeat_index: PositiveInt
    enforcement_mode: EnforcementMode
    task_prompt: NonEmptyStr
    task_output_contract_id: NonEmptyStr
    replay_target_aliases: tuple[ArtifactAliasRef, ...]


class T17LiveMatrix(StrictModel):
    """一个模型阶段的完整核心与 Replay 调度身份。"""

    schema_version: Literal["0.1"] = "0.1"
    id: NonEmptyStr
    preregistration_id: NonEmptyStr
    stage: T17LiveStage
    simulation_only_until_authorized: Literal[True] = True
    provider: ProviderConfig
    budget: BudgetConfig
    scheduled_core_trials: PositiveInt
    scheduled_replay_pairs: PositiveInt
    trials: Annotated[tuple[T17LiveTrial, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def require_exact_counts_and_unique_trials(self) -> Self:
        """核心和 Replay 计数必须由 Trial 内容机械复算。"""
        trial_ids = tuple(item.trial_id for item in self.trials)
        if len(set(trial_ids)) != len(trial_ids):
            raise PydanticCustomError("t17_live_trial_duplicate", "Trial ID 不得重复")
        if self.scheduled_core_trials != len(self.trials):
            raise PydanticCustomError(
                "t17_live_core_count_mismatch",
                "scheduled_core_trials 必须等于 trials 数量",
            )
        expected_replays = sum(len(item.replay_target_aliases) for item in self.trials)
        if self.scheduled_replay_pairs != expected_replays:
            raise PydanticCustomError(
                "t17_live_replay_count_mismatch",
                "scheduled_replay_pairs 必须由 counterfactual 机械生成",
            )
        return self


def load_live_preregistration(path: Path) -> T17LivePreregistration:
    """读取默认禁止 live 的 T17 预注册。"""
    return validate_yaml_document(path, T17LivePreregistration)


def load_live_matrix(path: Path) -> T17LiveMatrix:
    """读取一份静态 T17 真实模型 Matrix。"""
    return validate_yaml_document(path, T17LiveMatrix)


@dataclass(frozen=True, slots=True)
class _LiveVariantDesign:
    """Live condition ID、canonical source variant 与执行模式。"""

    variant: str
    source_variant: str
    measurement: T17VariantMeasurement
    enforcement_mode: EnforcementMode


def build_live_matrix(
    project_root: Path,
    registration: T17LivePreregistration,
    registry: T17ScenarioMeasurementRegistry,
    stage: T17LiveStage,
) -> T17LiveMatrix:
    """从 24 个真实 variant、模板和 repeat 机械生成阶段 Matrix。"""
    if registry.id != registration.scenario_registry_id:
        raise PydanticCustomError(
            "t17_registry_id_mismatch",
            "预注册与场景注册表 ID 不一致",
        )
    variants = _live_variant_designs(project_root, registry, stage)
    templates, repeats, provider, budget = _stage_design(registration, stage)
    scenarios = {
        item.measurement.scenario.scenario.root: validate_yaml_document(
            project_root / item.measurement.scenario.scenario.root,
            Scenario,
        )
        for item in variants
    }
    trials: list[T17LiveTrial] = []
    for item in variants:
        specification = item.measurement.scenario
        scenario = scenarios[specification.scenario.root]
        replay_targets = tuple(value.target for value in scenario.counterfactuals)
        for template in templates:
            semantic_id = f"{item.variant}-{template.template_id}"
            trials.extend(
                T17LiveTrial(
                    trial_id=f"t17-{stage.value}-{semantic_id}-r{repeat}",
                    variant=item.variant,
                    source_variant=item.source_variant,
                    scenario=specification.scenario,
                    scenario_id=specification.scenario_id,
                    semantic_instance_id=semantic_id,
                    semantic_template_id=template.template_id,
                    repeat_index=repeat,
                    enforcement_mode=item.enforcement_mode,
                    task_prompt=f"{template.prefix}{scenario.task.prompt}",
                    task_output_contract_id=specification.task_output_contract_id,
                    replay_target_aliases=replay_targets,
                )
                for repeat in range(1, repeats + 1)
            )
    replay_count = sum(
        [len(item.replay_target_aliases) for item in trials],
        start=0,
    )
    return T17LiveMatrix(
        id=f"t17-{stage.value}-matrix-v1",
        preregistration_id=registration.id,
        stage=stage,
        provider=provider,
        budget=budget,
        scheduled_core_trials=len(trials),
        scheduled_replay_pairs=replay_count,
        trials=tuple(trials),
    )


def write_live_matrix(path: Path, matrix: T17LiveMatrix) -> None:
    """以稳定字段顺序写出机械生成的 Matrix。"""
    path.write_text(
        yaml.safe_dump(
            matrix.model_dump(mode="json"),
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
        newline="\n",
    )


def _stage_design(
    registration: T17LivePreregistration,
    stage: T17LiveStage,
) -> tuple[tuple[T17SemanticTemplate, ...], int, ProviderConfig, BudgetConfig]:
    match stage:
        case T17LiveStage.CANARY:
            return (
                registration.semantic_templates[:1],
                1,
                registration.model1_provider,
                registration.model1_budget,
            )
        case T17LiveStage.MODEL1:
            return (
                registration.semantic_templates,
                registration.repeats_per_instance,
                registration.model1_provider,
                registration.model1_full_budget,
            )
        case T17LiveStage.MODEL2_CANARY:
            return (
                registration.semantic_templates[:1],
                1,
                registration.model2_provider,
                registration.model2_budget,
            )
        case T17LiveStage.MODEL2:
            return (
                registration.semantic_templates,
                registration.repeats_per_instance,
                registration.model2_provider,
                registration.model2_full_budget,
            )
        case T17LiveStage.DEFENSE:
            return (
                registration.semantic_templates,
                registration.repeats_per_instance,
                registration.model1_provider,
                registration.defense_budget,
            )
        case unreachable:
            assert_never(unreachable)


def _live_variant_designs(
    project_root: Path,
    registry: T17ScenarioMeasurementRegistry,
    stage: T17LiveStage,
) -> tuple[_LiveVariantDesign, ...]:
    measurements = {
        item.variant: item for item in expand_variant_measurements(project_root, registry)
    }
    base = validate_yaml_document(
        project_root / registry.matrix.root,
        ExperimentMatrix,
    )
    if stage is not T17LiveStage.DEFENSE:
        return tuple(
            _LiveVariantDesign(
                item.variant,
                item.variant,
                measurements[item.variant],
                item.enforcement_mode,
            )
            for item in base.variants
        )
    grouped: dict[str, list[ExperimentVariant]] = {}
    for variant in base.variants:
        grouped.setdefault(defense_base_key(variant), []).append(variant)
    if len(grouped) != EXPECTED_DEFENSE_BASE_CONFIGS:
        raise PydanticCustomError(
            "t17_defense_base_count",
            "去除 defense 轴后必须恰有 21 个基础配置",
        )
    complements = []
    for values in grouped.values():
        modes = {item.enforcement_mode for item in values}
        if len(modes) != 1:
            continue
        source = values[0]
        mode = (
            EnforcementMode.ENFORCE
            if source.enforcement_mode is EnforcementMode.MONITOR
            else EnforcementMode.MONITOR
        )
        complements.append(
            _LiveVariantDesign(
                f"{source.variant}-defense-{mode.value}",
                source.variant,
                measurements[source.variant],
                mode,
            )
        )
    if len(complements) != EXPECTED_DEFENSE_COMPLEMENTS:
        raise PydanticCustomError(
            "t17_defense_complement_count",
            "Defense 补集必须恰有 18 个模式",
        )
    return tuple(complements)


def defense_base_key(variant: ExperimentVariant) -> str:
    """返回排除 condition ID 与 enforcement mode 的基础配置键。"""
    payload = variant.model_dump(
        mode="json",
        exclude={"variant", "enforcement_mode"},
    )
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
