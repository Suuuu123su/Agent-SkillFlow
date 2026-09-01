"""T16-D.2 v3.1 Canary 的 Trial 与阶段摘要。"""

from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, Field, model_validator
from pydantic_core import PydanticCustomError

from skillflow.experiment.t16.live_usage_store import (
    ActualUsageStatus,
    LiveTrialTerminalStatus,
)
from skillflow.experiment.t16.provider import TokenUsage
from skillflow.experiment.t16.task_success_live_models import T16D2StopReason
from skillflow.models.base import NonEmptyStr, StrictModel

NonNegativeInt = Annotated[int, Field(ge=0)]
NonNegativeMoney = Annotated[Decimal, Field(ge=0)]
Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class T16D2CanaryTrialSummary(StrictModel):
    """一条完整或 Partial Canary 的可审计结果。"""

    trial_id: NonEmptyStr
    condition_id: NonEmptyStr
    agent_steps: NonNegativeInt
    completed_session_indices: tuple[NonNegativeInt, ...]
    terminal_status: LiveTrialTerminalStatus
    actual_usage_status: ActualUsageStatus
    observed_token_usage: TokenUsage | None
    observed_estimated_cost_usd: NonNegativeMoney | None
    task_success: bool | None
    target_effect_requested: bool | None
    target_effect_executed: bool | None
    receipt_id: NonEmptyStr | None
    refusal: bool | None
    no_call: bool | None
    schema_rejection: bool | None
    provider_model_revision: NonEmptyStr | None

    @model_validator(mode="after")
    def require_explicit_na_and_receipt(self) -> Self:
        """Partial 结果使用 N/A；已执行 Effect 必须有 Receipt。"""
        if self.actual_usage_status is ActualUsageStatus.NOT_AVAILABLE:
            if self.observed_token_usage is not None:
                self._invalid("实际 Token 不可用时必须为 N/A")
            if self.observed_estimated_cost_usd is not None:
                self._invalid("实际费用不可用时必须为 N/A")
        elif self.observed_token_usage is None or self.observed_estimated_cost_usd is None:
            self._invalid("已有响应时必须保存已观察用量")
        if self.target_effect_executed is True and self.receipt_id is None:
            self._invalid("已执行 target Effect 必须绑定 Receipt")
        return self

    @staticmethod
    def _invalid(detail: str) -> None:
        raise PydanticCustomError("t16d2_canary_trial_summary_invalid", detail)


class T16D2CanaryRunSummary(StrictModel):
    """仅针对 11 条 Canary 的阶段验收，不代表完整 48 条实验。"""

    schema_version: Literal["0.1"] = "0.1"
    created_at: AwareDatetime
    status: Literal["PASSED", "BLOCKED"]
    protocol_id: Literal["t16-task-success-bridge-preregistration-v3.1"]
    config_id: NonEmptyStr
    config_sha256: Sha256Hex
    phase_contract_sha256: Sha256Hex
    scheduled: Literal[11] = 11
    observed: NonNegativeInt
    unrun: NonNegativeInt
    canary_gate_passed: bool
    stop_reason: T16D2StopReason | None = None
    stop_detail: NonEmptyStr | None = None
    infrastructure_invalid: NonNegativeInt
    pairs_complete: bool
    c1_harm_selector_shared: bool
    task_success_result_count: NonNegativeInt
    task_success_evidence_count: NonNegativeInt
    passed_assertion_count: NonNegativeInt
    failed_assertion_count: NonNegativeInt
    not_evaluable_assertion_count: NonNegativeInt
    task_success_true: NonNegativeInt
    task_success_false: NonNegativeInt
    task_success_na: NonNegativeInt
    target_effect_requested_count: NonNegativeInt
    target_effect_executed_count: NonNegativeInt
    target_effect_receipt_count: NonNegativeInt
    receipt_coverage_complete: bool
    actual_usage_status: ActualUsageStatus
    observed_token_usage: TokenUsage | None
    observed_estimated_cost_usd: NonNegativeMoney | None
    conservative_reserved_usd: NonNegativeMoney
    api_call_count: NonNegativeInt
    m2_target_actual_steps: NonNegativeInt | None
    provider_model_revisions: tuple[NonEmptyStr, ...]
    raw_records_sha256: Sha256Hex
    usage_journal_sha256: Sha256Hex
    trials: tuple[T16D2CanaryTrialSummary, ...]

    @model_validator(mode="after")
    def require_stage_consistency(self) -> Self:
        """把 PASSED 限定为 11 条技术证据全部可评估的状态。"""
        if self.observed + self.unrun != self.scheduled:
            self._invalid("Canary observed + unrun 必须等于 11")
        if self.actual_usage_status is ActualUsageStatus.NOT_AVAILABLE:
            if self.observed_token_usage is not None:
                self._invalid("阶段实际 Token 不可用时必须为 N/A")
            if self.observed_estimated_cost_usd is not None:
                self._invalid("阶段实际费用不可用时必须为 N/A")
        elif self.observed_token_usage is None or self.observed_estimated_cost_usd is None:
            self._invalid("阶段已有响应时必须保存已观察用量")
        if self.status == "PASSED":
            passed = (
                self.observed == self.scheduled
                and self.canary_gate_passed
                and self.stop_reason is None
                and self.infrastructure_invalid == 0
                and self.task_success_result_count == self.scheduled
                and self.not_evaluable_assertion_count == 0
                and self.pairs_complete
                and self.c1_harm_selector_shared
                and self.receipt_coverage_complete
            )
            if not passed:
                self._invalid("Canary PASSED 与技术验收字段不一致")
        return self

    @staticmethod
    def _invalid(detail: str) -> None:
        raise PydanticCustomError("t16d2_canary_summary_invalid", detail)
