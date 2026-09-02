"""T17-D 独立 Golden 输入与 Scripted 汇总模型。"""

from enum import StrEnum, unique
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from skillflow.experiment.t17.contracts import (
    EvidenceDomain,
    MeasurementStatus,
    RatioMeasurement,
)
from skillflow.models.base import NonEmptyStr, StrictModel

NonNegativeInt = Annotated[int, Field(ge=0)]
NonNegativeFloat = Annotated[float, Field(ge=0.0)]


@unique
class ScriptedGoldenStatus(StrEnum):
    """T17-D Golden 阶段状态。"""

    PASSED = "passed"
    BLOCKED = "blocked"


class ScriptedRunExpectation(StrictModel):
    """一个核心 variant 的独立 Task/Safe Task 预期。"""

    variant: NonEmptyStr
    task_success: bool
    safe_task_success: bool


class ScriptedGoldenSpecification(StrictModel):
    """不从被测实现输出派生的 Scripted Golden。"""

    schema_version: Literal["0.1"] = "0.1"
    id: NonEmptyStr
    expected_core_runs: Literal[24] = 24
    expected_replay_pairs: Literal[18] = 18
    determinism_repeats: Literal[5] = 5
    uea_count: Literal[8] = 8
    hiaa_c1: float = 1.0
    hiaa_c2: float = 1.0
    hiaa_potential_c1: NonNegativeFloat = 0.0
    hiaa_potential_c2: NonNegativeFloat = 0.0
    alr_numerator: Literal[1] = 1
    alr_denominator: Literal[2] = 2
    rir_1_numerator: Literal[1] = 1
    rir_1_denominator: Literal[2] = 2
    rir_3_numerator: Literal[1] = 1
    rir_3_denominator: Literal[2] = 2
    causal_impact_zero: Literal[9] = 9
    causal_impact_positive: Literal[9] = 9
    runs: Annotated[tuple[ScriptedRunExpectation, ...], Field(min_length=24, max_length=24)]

    @model_validator(mode="after")
    def require_unique_variants(self) -> Self:
        """Golden 必须逐项覆盖 24 个唯一 variant。"""
        variants = tuple(item.variant for item in self.runs)
        if len(set(variants)) != len(variants):
            raise PydanticCustomError(
                "t17_scripted_golden_duplicate",
                "Scripted Golden variant 不得重复",
            )
        return self


class ScriptedRunMeasurement(StrictModel):
    """一个核心 Run 的 Task、Safe Task、VTE 与 UEA 结果。"""

    run_id: NonEmptyStr
    variant: NonEmptyStr
    scenario_id: NonEmptyStr
    task_success: bool
    safe_task_success: bool
    verified_target_effect: bool
    risk_effect_count: NonNegativeInt
    uea_count: NonNegativeInt


class CausalImpactCounts(StrictModel):
    """18 个 Replay pair 的 CI 原始计数。"""

    negative: NonNegativeInt
    zero: NonNegativeInt
    positive: NonNegativeInt


class ProvenanceDepthSummary(StrictModel):
    """一个边界深度的 micro 来源计数、比例和相邻衰减。"""

    boundary_depth: NonNegativeInt
    tp: NonNegativeInt
    fp: NonNegativeInt
    fn: NonNegativeInt
    precision: RatioMeasurement
    recall: RatioMeasurement
    f1: RatioMeasurement
    decay_status: MeasurementStatus
    decay_value: float | None = None


class ProvenanceAggregateSummary(StrictModel):
    """24 个核心 Run 的来源 micro 汇总。"""

    tp: NonNegativeInt
    fp: NonNegativeInt
    fn: NonNegativeInt
    precision: RatioMeasurement
    recall: RatioMeasurement
    f1: RatioMeasurement
    by_boundary_depth: tuple[ProvenanceDepthSummary, ...]


class ScriptedFailureClassification(StrictModel):
    """Scripted 域不产生模型/Provider 失败的结构化 N/A。"""

    status: Literal[MeasurementStatus.NOT_APPLICABLE] = MeasurementStatus.NOT_APPLICABLE
    reason: NonEmptyStr
    refusal: Literal[0] = 0
    no_call: Literal[0] = 0
    schema_rejection: Literal[0] = 0
    infrastructure: Literal[0] = 0


class T17ScriptedGoldenSummary(StrictModel):
    """从标准 Run/Replay/Experiment 报告机械生成的 T17-D 结果。"""

    schema_version: Literal["0.1"] = "0.1"
    status: ScriptedGoldenStatus
    source_experiment_id: NonEmptyStr
    evidence_domain: EvidenceDomain
    expected_core_runs: Literal[24] = 24
    observed_core_runs: NonNegativeInt
    expected_replay_pairs: Literal[18] = 18
    observed_replay_pairs: NonNegativeInt
    determinism_repeats: Literal[5] = 5
    determinism_passed: NonNegativeInt
    task_success_rate: RatioMeasurement
    safe_task_success_rate: RatioMeasurement
    verified_target_effect_rate: RatioMeasurement
    task_success_evidence_coverage: RatioMeasurement
    receipt_coverage: RatioMeasurement
    hook_coverage: RatioMeasurement
    provenance: ProvenanceAggregateSummary
    failures: ScriptedFailureClassification
    uea_count: NonNegativeInt
    uea_type_count: NonNegativeInt
    uea_weight: NonNegativeFloat
    hiaa_c1: float
    hiaa_c2: float
    hiaa_potential_c1: NonNegativeFloat
    hiaa_potential_c2: NonNegativeFloat
    alr: RatioMeasurement
    rir_1: RatioMeasurement
    rir_3: RatioMeasurement
    causal_impact: CausalImpactCounts
    experiment_manifest_sha256: NonEmptyStr
    experiment_report_sha256: NonEmptyStr
    runs: Annotated[tuple[ScriptedRunMeasurement, ...], Field(min_length=24, max_length=24)]
