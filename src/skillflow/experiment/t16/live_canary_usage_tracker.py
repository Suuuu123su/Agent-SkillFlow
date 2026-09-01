"""T16-D.2 v3.1 Canary 的 Trial 级逐响应用量状态机。"""

from decimal import Decimal
from typing import Literal

from skillflow.experiment.t16.budget import BudgetLedger
from skillflow.experiment.t16.live_agent_calls import ActualResponseUsage
from skillflow.experiment.t16.live_canary_usage_models import (
    CanaryUsageSink,
    CanaryUsageSnapshot,
    LiveCanaryMetadataDriftError,
    LiveCanaryUsageStoreError,
)
from skillflow.experiment.t16.live_record_builders import add_usage
from skillflow.experiment.t16.live_usage_store import LiveTrialTerminalStatus
from skillflow.experiment.t16.provider import TokenUsage


class LiveCanaryUsageTracker:
    """因逐调用累计职责而有意可变的一条 Trial 用量状态机。"""

    __slots__ = (
        "_finalized",
        "api_call_count",
        "completed_session_indices",
        "condition_id",
        "current_session_index",
        "journal",
        "last_model_revision",
        "observed_estimated_cost_usd",
        "observed_token_usage",
        "response_count",
        "run_reserved_usd",
        "total_reserved_usd",
        "trial_id",
    )

    def __init__(self, journal: CanaryUsageSink, trial_id: str, condition_id: str) -> None:
        """初始化一条尚未调用 Provider 的 Trial 状态。"""
        self.journal = journal
        self.trial_id = trial_id
        self.condition_id = condition_id
        self.api_call_count = 0
        self.response_count = 0
        self.total_reserved_usd = Decimal(0)
        self.run_reserved_usd = Decimal(0)
        self.observed_token_usage: TokenUsage | None = None
        self.observed_estimated_cost_usd: Decimal | None = None
        self.current_session_index: int | None = None
        self.last_model_revision: str | None = None
        self.completed_session_indices: tuple[int, ...] = ()
        self._finalized = False

    def activate_session(self, session_index: int) -> None:
        """绑定下一次响应所属的 Session。"""
        self._require_active()
        if self.current_session_index is not None and (
            self.current_session_index not in self.completed_session_indices
        ):
            detail = "Canary 前一 Session 尚未完成"
            raise LiveCanaryUsageStoreError(detail)
        self.current_session_index = session_index

    def complete_session(self, session_index: int) -> None:
        """记录已经构造并返回的 Session。"""
        self._require_active()
        if self.current_session_index != session_index:
            detail = "Canary Session 完成边界错配"
            raise LiveCanaryUsageStoreError(detail)
        if session_index in self.completed_session_indices:
            detail = "Canary Session 被重复完成"
            raise LiveCanaryUsageStoreError(detail)
        self.completed_session_indices = (*self.completed_session_indices, session_index)

    def record_attempt(self, budget: BudgetLedger) -> None:
        """在调用前预算已 fsync 后记录保守预留和 Step。"""
        self._require_active()
        if self.current_session_index is None:
            detail = "Canary 调用缺少 Session 绑定"
            raise LiveCanaryUsageStoreError(detail)
        self.api_call_count += 1
        self.total_reserved_usd = budget.total_spent_usd
        self.run_reserved_usd = budget.run_spent_usd

    def record_response(self, usage: TokenUsage, estimated_cost_usd: Decimal) -> None:
        """拒绝缺少 Provider/model 元数据的旧式响应路径。"""
        del usage, estimated_cost_usd
        detail = "Canary 响应必须携带 Provider/model 元数据"
        raise LiveCanaryUsageStoreError(detail)

    def record_detailed_response(self, response: ActualResponseUsage) -> None:
        """响应返回后立即保存本次与累计 Token、费用及 Session/Step。"""
        self._require_active()
        if self.current_session_index is None:
            detail = "Canary 响应缺少 Session 绑定"
            raise LiveCanaryUsageStoreError(detail)
        self.response_count += 1
        self.last_model_revision = response.model_revision
        if response.budget is not None:
            self.total_reserved_usd = response.budget.total_spent_usd
            self.run_reserved_usd = response.budget.run_spent_usd
        self.observed_token_usage = (
            response.token_usage
            if self.observed_token_usage is None
            else add_usage(self.observed_token_usage, response.token_usage)
        )
        self.observed_estimated_cost_usd = (
            response.estimated_cost_usd
            if self.observed_estimated_cost_usd is None
            else self.observed_estimated_cost_usd + response.estimated_cost_usd
        )
        self.journal.append_snapshot(self._snapshot("response", response))
        if response.provider != self.journal.expected_provider:
            detail = "Provider 与冻结 Canary 配置不一致"
            raise LiveCanaryMetadataDriftError(detail)
        if response.model_id != self.journal.expected_model_id:
            detail = "Model ID 与冻结 Canary 配置不一致"
            raise LiveCanaryMetadataDriftError(detail)
        if response.model_revision != self.journal.expected_model_id:
            detail = "Model revision 与冻结 Canary 配置不一致"
            raise LiveCanaryMetadataDriftError(detail)

    def finalize(self, status: LiveTrialTerminalStatus, stop_detail: str | None = None) -> None:
        """在 Runner finally 中保存完整或 Partial Trial 终态。"""
        self._require_active()
        self.journal.append_snapshot(self._snapshot("terminal", None, status, stop_detail))
        self._finalized = True

    def _snapshot(
        self,
        event_type: Literal["response", "terminal"],
        response: ActualResponseUsage | None,
        terminal_status: LiveTrialTerminalStatus | None = None,
        stop_detail: str | None = None,
    ) -> CanaryUsageSnapshot:
        return CanaryUsageSnapshot(
            event_type=event_type,
            trial_id=self.trial_id,
            condition_id=self.condition_id,
            session_index=self.current_session_index,
            agent_step=self.api_call_count or None,
            provider=(
                response.provider if response is not None else self.journal.expected_provider
            ),
            model_id=(
                response.model_id if response is not None else self.journal.expected_model_id
            ),
            model_revision=(
                response.model_revision if response is not None else self.last_model_revision
            ),
            api_call_count=self.api_call_count,
            response_count=self.response_count,
            total_reserved_usd=self.total_reserved_usd,
            run_reserved_usd=self.run_reserved_usd,
            response_token_usage=(response.token_usage if response is not None else None),
            response_estimated_cost_usd=(
                response.estimated_cost_usd if response is not None else None
            ),
            observed_token_usage=self.observed_token_usage,
            observed_estimated_cost_usd=self.observed_estimated_cost_usd,
            completed_session_indices=self.completed_session_indices,
            terminal_status=terminal_status,
            stop_detail=stop_detail,
        )

    def _require_active(self) -> None:
        if self._finalized:
            detail = f"Canary Trial 用量已终结: {self.trial_id}"
            raise LiveCanaryUsageStoreError(detail)
