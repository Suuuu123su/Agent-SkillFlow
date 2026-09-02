"""T17-C 场景任务、风险 Effect、Hook 与指标适用性注册表。"""

from dataclasses import dataclass
from enum import StrEnum, unique
from pathlib import Path
from typing import Annotated, Final, Self

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from skillflow.experiment.t17.contracts import HookName
from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.enums import EnforcementMode
from skillflow.models.matrix import ExperimentMatrix
from skillflow.models.references import ArtifactAliasRef, EffectSelectorRef, ScenarioPath
from skillflow.models.scenario import Scenario
from skillflow.policy.reasons import PolicyReasonCode
from skillflow.validation import validate_yaml_document

EXPECTED_VARIANT_COUNT: Final = 24


@unique
class T17MetricName(StrEnum):
    """场景可声明适用的 T17 指标。"""

    TASK_SUCCESS = "task_success"
    SAFE_TASK_SUCCESS = "safe_task_success"
    VERIFIED_TARGET_EFFECT = "verified_target_effect"
    UEA = "uea"
    PROVENANCE = "provenance"
    CAUSAL_IMPACT = "causal_impact"
    HIAA = "hiaa"
    ALR = "alr"
    RIR_1 = "rir_1"
    RIR_3 = "rir_3"
    EFFICIENCY = "efficiency"


@unique
class T17ConditionKind(StrEnum):
    """良性控制与风险条件的预注册任务类别。"""

    BENIGN_CONTROL = "benign_control"
    RISK = "risk"


class T17ScenarioMeasurement(StrictModel):
    """一个 T12 Scenario 的正常任务、风险 Effect 和证据合同。"""

    scenario_id: NonEmptyStr
    scenario: ScenarioPath
    condition_kind: T17ConditionKind
    task_output_contract_id: NonEmptyStr
    task_artifact_aliases: Annotated[tuple[ArtifactAliasRef, ...], Field(min_length=1)]
    task_required_effect_aliases: tuple[EffectSelectorRef, ...] = ()
    legitimate_effect_aliases: tuple[EffectSelectorRef, ...] = ()
    risk_effect_aliases: tuple[EffectSelectorRef, ...] = ()
    required_hooks: Annotated[tuple[HookName, ...], Field(min_length=1)]
    applicable_metrics: Annotated[tuple[T17MetricName, ...], Field(min_length=1)]
    expected_reason_codes: tuple[PolicyReasonCode, ...] = ()

    @model_validator(mode="after")
    def require_task_and_risk_separation(self) -> Self:
        """合法与风险 Effect 不得重叠，基础指标和 Hook 必须齐全。"""
        legitimate = {item.alias for item in self.legitimate_effect_aliases}
        risks = {item.alias for item in self.risk_effect_aliases}
        task_required = {item.alias for item in self.task_required_effect_aliases}
        if legitimate & risks:
            raise PydanticCustomError(
                "t17_effect_role_overlap",
                "legitimate 与 risk Effect alias 不得重叠",
            )
        if not task_required.issubset(legitimate | risks):
            raise PydanticCustomError(
                "t17_task_effect_role_missing",
                "task required Effect 必须同时声明为 legitimate 或 risk",
            )
        required_hooks = set(self.required_hooks)
        if not {HookName.AUTHORIZATION, HookName.TASK_SUCCESS}.issubset(required_hooks):
            raise PydanticCustomError(
                "t17_required_hook_missing",
                "每个场景必须要求 authorization 与 task_success Hook",
            )
        required_metrics = {
            T17MetricName.TASK_SUCCESS,
            T17MetricName.SAFE_TASK_SUCCESS,
            T17MetricName.VERIFIED_TARGET_EFFECT,
            T17MetricName.UEA,
            T17MetricName.PROVENANCE,
            T17MetricName.EFFICIENCY,
        }
        if not required_metrics.issubset(self.applicable_metrics):
            raise PydanticCustomError(
                "t17_base_metric_missing",
                "每个场景必须声明基础任务、风险、来源和效率指标",
            )
        return self


class T17ScenarioMeasurementRegistry(StrictModel):
    """16 个 T12 Scenario 与 24 个 Matrix variant 的绑定源。"""

    schema_version: str = "0.1"
    id: NonEmptyStr
    matrix: ScenarioPath
    scenarios: Annotated[tuple[T17ScenarioMeasurement, ...], Field(min_length=16, max_length=16)]

    @model_validator(mode="after")
    def require_unique_scenarios(self) -> Self:
        """Scenario ID 与路径必须各自唯一。"""
        identifiers = tuple(item.scenario_id for item in self.scenarios)
        paths = tuple(item.scenario.root for item in self.scenarios)
        if len(set(identifiers)) != len(identifiers) or len(set(paths)) != len(paths):
            raise PydanticCustomError(
                "t17_scenario_registry_duplicate",
                "Scenario ID 与路径不得重复",
            )
        return self


class T17VariantMeasurement(StrictModel):
    """一个真实 Matrix variant 绑定的场景测量合同。"""

    variant: NonEmptyStr
    enforcement_mode: EnforcementMode
    scenario: T17ScenarioMeasurement


@dataclass(frozen=True, slots=True)
class ScenarioMeasurementBindingError(ValueError):
    """注册表、Matrix 与 Scenario DSL 之间存在漂移。"""

    identifier: str
    detail: str

    def __str__(self) -> str:
        """返回稳定绑定诊断。"""
        return f"{self.identifier}:{self.detail}"


def load_scenario_measurement_registry(path: Path) -> T17ScenarioMeasurementRegistry:
    """读取并严格校验 T17-C 静态注册表。"""
    return validate_yaml_document(path, T17ScenarioMeasurementRegistry)


def expand_variant_measurements(
    project_root: Path,
    registry: T17ScenarioMeasurementRegistry,
) -> tuple[T17VariantMeasurement, ...]:
    """通过真实 Matrix/Scenario 模型展开并验证全部 variant。"""
    matrix = validate_yaml_document(project_root / registry.matrix.root, ExperimentMatrix)
    by_path = {item.scenario.root: item for item in registry.scenarios}
    validated = {
        item.scenario.root: _validate_scenario(project_root, item) for item in registry.scenarios
    }
    variants = []
    for variant in matrix.variants:
        specification = by_path.get(variant.scenario.root)
        if specification is None:
            raise ScenarioMeasurementBindingError(
                variant.variant,
                "matrix_scenario_unregistered",
            )
        if validated[variant.scenario.root].id != specification.scenario_id:
            raise ScenarioMeasurementBindingError(
                variant.variant,
                "scenario_id_mismatch",
            )
        variants.append(
            T17VariantMeasurement(
                variant=variant.variant,
                enforcement_mode=variant.enforcement_mode,
                scenario=specification,
            )
        )
    if len(variants) != EXPECTED_VARIANT_COUNT:
        raise ScenarioMeasurementBindingError(registry.id, "expected_24_variants")
    return tuple(variants)


def _validate_scenario(
    project_root: Path,
    specification: T17ScenarioMeasurement,
) -> Scenario:
    scenario = validate_yaml_document(project_root / specification.scenario.root, Scenario)
    artifact_aliases = {
        alias.alias
        for session in scenario.sessions
        for step in session.steps
        for alias in (*step.outputs, *(item.alias for item in step.tool_outputs))
    }
    required_artifacts = {item.alias for item in specification.task_artifact_aliases}
    if not required_artifacts.issubset(artifact_aliases):
        raise ScenarioMeasurementBindingError(
            specification.scenario_id,
            "task_artifact_alias_missing",
        )
    selectors = {item.alias for item in scenario.effect_selectors}
    required_effects = {
        item.alias
        for item in (
            *specification.legitimate_effect_aliases,
            *specification.risk_effect_aliases,
            *specification.task_required_effect_aliases,
        )
    }
    if not required_effects.issubset(selectors):
        raise ScenarioMeasurementBindingError(
            specification.scenario_id,
            "effect_alias_missing",
        )
    return scenario
