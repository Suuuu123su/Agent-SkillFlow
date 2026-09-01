"""T16-C 真实模型阶段运行摘要与停止原因。"""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum, unique
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from skillflow.experiment.t16.provider import TokenUsage
from skillflow.models.base import NonEmptyStr, StrictModel

NonNegativeInt = Annotated[int, Field(ge=0)]
NonNegativeMoney = Annotated[Decimal, Field(ge=0)]


@unique
class LivePhase(StrEnum):
    """T16-C 只允许先 Smoke、再单模型完整矩阵。"""

    SMOKE = "smoke"
    MODEL1 = "model1"


@unique
class LiveStopReason(StrEnum):
    """必须立即停止且保留既有证据的原因。"""

    BUDGET_LIMIT = "budget_limit"
    CONTRACT_MISMATCH = "contract_mismatch"
    GATEWAY_CRASH = "gateway_crash"
    INFRASTRUCTURE_FAILURE = "infrastructure_failure"


class LiveResultCounts(StrictModel):
    """互斥 Trial 三分类的原始计数。"""

    harm: NonNegativeInt
    completed_without_harm: NonNegativeInt
    invalid: NonNegativeInt

    @property
    def total(self) -> int:
        """返回三分类总数。"""
        return self.harm + self.completed_without_harm + self.invalid


class LiveFailureCounts(StrictModel):
    """不与拒绝/no-call 混淆的失败子类计数。"""

    refusal: NonNegativeInt
    no_call: NonNegativeInt
    schema_rejection: NonNegativeInt
    timeout: NonNegativeInt
    rate_limit: NonNegativeInt
    provider_error: NonNegativeInt
    gateway_crash: NonNegativeInt

    @property
    def infrastructure_total(self) -> int:
        """返回与模型输出无关的基础设施失败总数。"""
        return self.timeout + self.rate_limit + self.provider_error + self.gateway_crash

    def gate_blocking_total(self, phase: LivePhase) -> int:
        """Smoke 阻断配置/基础设施错误；正式矩阵保留单链 invalid。"""
        if phase is LivePhase.SMOKE:
            return self.infrastructure_total + self.schema_rejection
        return 0


class LivePhaseSummary(StrictModel):
    """一阶段真实模型运行的可恢复汇总，不把本地 Effect 写成外发。"""

    schema_version: Literal["0.1"] = "0.1"
    simulation_only: Literal[False] = False
    live_model: Literal[True] = True
    external_effects_simulated: Literal[True] = True
    phase: LivePhase
    model_id: NonEmptyStr
    model_revision_config: NonEmptyStr
    matrix_id: NonEmptyStr
    expected_trial_count: NonNegativeInt
    completed_trial_count: NonNegativeInt
    unique_trial_id_count: NonNegativeInt
    resumed_trial_count: NonNegativeInt
    new_trial_count: NonNegativeInt
    stopped: bool
    stop_reason: LiveStopReason | None = None
    stop_detail: NonEmptyStr | None = None
    live_gate_passed: bool
    result_counts: LiveResultCounts
    failure_counts: LiveFailureCounts
    token_usage: TokenUsage
    api_call_count: NonNegativeInt
    actual_estimated_cost_usd: NonNegativeMoney
    conservative_reserved_usd: NonNegativeMoney
    trial_results_sha256: NonEmptyStr
    budget_journal_sha256: NonEmptyStr
    provenance_not_available_count: NonNegativeInt

    @model_validator(mode="after")
    def require_recomputable_counts_and_gate(self) -> Self:
        """拒绝不完整计数或把基础设施失败写成 Gate 通过。"""
        if self.result_counts.total != self.completed_trial_count:
            self._invalid("三分类总数必须等于已完成 Trial 数")
        if self.unique_trial_id_count != self.completed_trial_count:
            self._invalid("已保存 live trial_id 必须唯一")
        if self.resumed_trial_count + self.new_trial_count != self.completed_trial_count:
            self._invalid("恢复与新增 Trial 数必须覆盖全部已保存结果")
        if self.completed_trial_count > self.expected_trial_count:
            self._invalid("已完成 Trial 不能超过 Matrix")
        if self.stopped != (self.stop_reason is not None):
            self._invalid("stopped 与 stop_reason 不一致")
        complete = self.completed_trial_count == self.expected_trial_count and not self.stopped
        expected_gate = complete and self.failure_counts.gate_blocking_total(self.phase) == 0
        if self.live_gate_passed != expected_gate:
            self._invalid("Live Gate 必须由完整性和基础设施失败机械决定")
        if self.provenance_not_available_count != self.completed_trial_count:
            self._invalid("缺少来源 Hook 时每条结果都必须记录结构化 N/A")
        return self

    @staticmethod
    def _invalid(detail: str) -> None:
        raise PydanticCustomError("t16c_phase_summary_invalid", detail)


@dataclass(frozen=True, slots=True)
class LiveGatewayCrashError(RuntimeError):
    """受控注入或边界包装后的 Gateway 崩溃；不携带请求内容。"""

    def __str__(self) -> str:
        """返回不含输入或响应的稳定诊断。"""
        return LiveStopReason.GATEWAY_CRASH.value
