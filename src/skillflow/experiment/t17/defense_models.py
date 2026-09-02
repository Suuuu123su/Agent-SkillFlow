"""T17-H Monitor/Enforce 安全—效用与开销报告模型。"""

from decimal import Decimal
from typing import Annotated, Literal, Never, Self

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from skillflow.experiment.t17.contracts import (
    MeasurementStatus,
    RatioMeasurement,
)
from skillflow.experiment.t17.live_reference_client import ReferenceLiveTelemetry
from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.enums import EnforcementMode
from skillflow.models.reports import ExperimentRiskReport

NonNegativeInt = Annotated[int, Field(ge=0)]
Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
GAIN_TOLERANCE = 1e-12


class T17DefenseModeMetrics(StrictModel):
    """一个模式下 21 基础配置的风险、任务与总用量。"""

    mode: EnforcementMode
    scheduled_core_trials: NonNegativeInt
    scheduled_replay_pairs: NonNegativeInt
    task_success_rate: RatioMeasurement
    safe_task_success_rate: RatioMeasurement
    benign_refusal_rate: RatioMeasurement
    risk_vte_rate: RatioMeasurement
    risk_uea_affected_rate: RatioMeasurement
    uea_count: NonNegativeInt
    standard_risk_report: ExperimentRiskReport
    telemetry: ReferenceLiveTelemetry


class T17SecurityGain(StrictModel):
    """单个风险指标的 monitor-enforce，禁止加权合并。"""

    metric: NonEmptyStr
    status: MeasurementStatus
    monitor_value: float | None = None
    enforce_value: float | None = None
    security_gain: float | None = None
    reason: NonEmptyStr | None = None
    evidence_ids: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def require_gain_contract(self) -> Self:
        """Measured gain 必须由两个点估计机械相减。"""
        if self.status is MeasurementStatus.MEASURED:
            monitor = self.monitor_value
            enforce = self.enforce_value
            gain = self.security_gain
            if monitor is None or enforce is None or gain is None:
                self._invalid("measured SecurityGain 缺少数值")
            if abs(gain - (monitor - enforce)) > GAIN_TOLERANCE:
                self._invalid("SecurityGain 必须等于 monitor-enforce")
        elif self.reason is None:
            self._invalid("非 measured SecurityGain 必须说明原因")
        return self

    @staticmethod
    def _invalid(detail: str) -> Never:
        raise PydanticCustomError("t17_security_gain_invalid", detail)


class T17DefenseReport(StrictModel):
    """630 core/540 Replay 的无加权安全—效用报告。"""

    schema_version: Literal["0.1"] = "0.1"
    report_scope: Literal["t17_defense"] = "t17_defense"
    report_id: NonEmptyStr
    model_revision: NonEmptyStr
    source_phase_sha256: dict[NonEmptyStr, Sha256Hex]
    combined_core_trials: Literal[630]
    combined_replay_pairs: Literal[540]
    monitor: T17DefenseModeMetrics
    enforce: T17DefenseModeMetrics
    security_gains: tuple[T17SecurityGain, ...]
    utility_loss: float
    safe_tsr_delta: float
    over_defense_rate: RatioMeasurement
    estimated_cost_delta_enforce_minus_monitor_usd: Decimal
    latency_delta_enforce_minus_monitor_ms: int
    token_delta_enforce_minus_monitor: int
    api_call_delta_enforce_minus_monitor: int
    agent_step_delta_enforce_minus_monitor: int
    weighted_security_score: None = None
    complete: bool
