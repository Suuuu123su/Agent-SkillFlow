"""T17 Phase 报告的区间、风险、因果、稳定性与效率模型。"""

from decimal import Decimal
from enum import StrEnum, unique
from typing import Annotated, Literal, Never, Self

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from skillflow.experiment.t17.contracts import (
    EvidenceDomain,
    MeasurementStatus,
    RatioMeasurement,
)
from skillflow.experiment.t17.live_attempt_models import T17LiveStageSummary
from skillflow.experiment.t17.live_reference_client import ReferenceLiveTelemetry
from skillflow.experiment.t17.scripted_models import ProvenanceAggregateSummary
from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.reports import ExperimentRiskReport

NonNegativeInt = Annotated[int, Field(ge=0)]
NonNegativeFloat = Annotated[float, Field(ge=0)]
NonNegativeMoney = Annotated[Decimal, Field(ge=0)]
Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_SEED = 17_017


@unique
class T17IntervalMethod(StrEnum):
    """T17 允许的两类 95% 区间。"""

    WILSON_CHAIN_DESCRIPTIVE = "wilson_chain_descriptive"
    CLUSTER_BOOTSTRAP = "cluster_bootstrap"


class T17IntervalEstimate(StrictModel):
    """带状态、方法、点估计和固定重采样元数据的区间。"""

    status: MeasurementStatus
    method: T17IntervalMethod
    confidence: Annotated[float, Field(ge=0, le=1)] = 0.95
    point: float | None = None
    lower: float | None = None
    upper: float | None = None
    resamples: int | None = None
    seed: int | None = None
    reason: NonEmptyStr | None = None
    evidence_ids: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def require_interval_contract(self) -> Self:
        """Measured 必须有闭区间；其他状态不得伪造界限。"""
        if self.status is MeasurementStatus.MEASURED:
            point = self.point
            lower = self.lower
            upper = self.upper
            if point is None or lower is None or upper is None:
                self._invalid("measured 区间缺少 point/lower/upper")
            if not lower <= point <= upper:
                self._invalid("区间必须满足 lower<=point<=upper")
            if self.method is T17IntervalMethod.CLUSTER_BOOTSTRAP:
                if self.resamples != BOOTSTRAP_RESAMPLES or self.seed != BOOTSTRAP_SEED:
                    self._invalid("Bootstrap 必须固定 10000 次和 seed 17017")
            elif self.resamples is not None or self.seed is not None:
                self._invalid("Wilson 区间不得声明 Bootstrap 元数据")
        else:
            if any(value is not None for value in (self.point, self.lower, self.upper)):
                self._invalid("非 measured 区间不得携带数值")
            if self.reason is None:
                self._invalid("非 measured 区间必须说明原因")
        return self

    @staticmethod
    def _invalid(detail: str) -> Never:
        raise PydanticCustomError("t17_interval_invalid", detail)


class T17UeaSummary(StrictModel):
    """UEA 实例、类型、权重与受影响 Trial 比例。"""

    uea_count: NonNegativeInt
    uea_type_count: NonNegativeInt
    uea_weight: NonNegativeFloat
    affected_trial_rate: RatioMeasurement
    effect_ids: tuple[NonEmptyStr, ...]
    canonical_effect_keys: tuple[NonEmptyStr, ...]


class T17CausalImpactSummary(StrictModel):
    """Replay CI 三值计数及非零影响率。"""

    negative_count: NonNegativeInt
    zero_count: NonNegativeInt
    positive_count: NonNegativeInt
    nonzero_rate: RatioMeasurement
    replay_ids: tuple[NonEmptyStr, ...]
    confirmed_influence_evidence_ids: tuple[NonEmptyStr, ...]


class T17EfficiencySummary(StrictModel):
    """阶段总用量与逐调度单元的描述性开销。"""

    unit_count: NonNegativeInt
    telemetry: ReferenceLiveTelemetry
    agent_steps_mean: NonNegativeFloat | None
    agent_steps_p95: NonNegativeFloat | None
    api_calls_mean: NonNegativeFloat | None
    api_calls_p95: NonNegativeFloat | None
    latency_ms_mean: NonNegativeFloat | None
    latency_ms_p95: NonNegativeFloat | None
    estimated_cost_usd_mean: NonNegativeMoney | None
    estimated_cost_usd_p95: NonNegativeMoney | None


class T17ProvenanceReport(StrictModel):
    """来源 micro 统计及其阶段完整性边界。"""

    status: MeasurementStatus
    observed_runs: NonNegativeInt
    scheduled_runs: NonNegativeInt
    metrics: ProvenanceAggregateSummary | None
    reason: NonEmptyStr | None = None

    @model_validator(mode="after")
    def require_provenance_status(self) -> Self:
        """完整阶段必须有 metrics；不完整阶段必须说明原因。"""
        if self.status is MeasurementStatus.MEASURED:
            if self.metrics is None or self.observed_runs != self.scheduled_runs:
                self._invalid("measured provenance 要求完整 Run 与 metrics")
        elif self.reason is None:
            self._invalid("非 measured provenance 必须说明原因")
        return self

    @staticmethod
    def _invalid(detail: str) -> None:
        raise PydanticCustomError("t17_provenance_report_invalid", detail)


class T17PhaseMetricsReport(StrictModel):
    """一个 Evidence Domain 内不可跨模型 pooling 的完整阶段指标。"""

    schema_version: Literal["0.1"] = "0.1"
    report_scope: Literal["t17_phase"] = "t17_phase"
    report_id: NonEmptyStr
    required_metrics_complete: bool
    evidence_domain: EvidenceDomain
    stage_summary: T17LiveStageSummary
    standard_risk_report: ExperimentRiskReport
    standard_risk_scope: Literal["scheduled_complete", "observed_only_sensitivity"]
    task_success_rate: RatioMeasurement
    safe_task_success_rate: RatioMeasurement
    benign_refusal_rate: RatioMeasurement
    verified_target_effect_rate: RatioMeasurement
    uea: T17UeaSummary
    provenance: T17ProvenanceReport
    causal_impact: T17CausalImpactSummary
    cluster_consistency: RatioMeasurement
    advanced_metric_statuses: dict[NonEmptyStr, MeasurementStatus]
    wilson_intervals: dict[NonEmptyStr, T17IntervalEstimate]
    bootstrap_intervals: dict[NonEmptyStr, T17IntervalEstimate]
    efficiency: T17EfficiencySummary
    source_artifact_sha256: dict[NonEmptyStr, Sha256Hex]
