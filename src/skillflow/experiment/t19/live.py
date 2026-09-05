"""复用已验证 DS 客户端，增加 T19 整链与重放剩余预算保护。"""

import os
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from skillflow.experiment.t17.v2.api_models import V2BudgetExhaustedError
from skillflow.experiment.t17.v2.live_client import V2LiveClient
from skillflow.experiment.t17.v2.run_models import UnitUsage
from skillflow.experiment.t17.v2.usage_summary import summarize_usage
from skillflow.experiment.t19.continuation import RecoveryIntent

MAX_CHAIN_STEPS = 16
MAX_INPUT_BYTES = 12000
MAX_CALL_USD = Decimal("0.00228928")


class T19LiveClient(V2LiveClient):
    """整个 campaign 保持一本追加账；新尝试带入此前保守占用。"""

    def open_accounted_journal(
        self, path: Path, phase_sha256: str, previous_reserved_usd: Decimal
    ) -> None:
        """先核对历史占用，不把新进程的零状态当可用余额。"""
        if (
            self.config.budget.max_agent_turns != MAX_CHAIN_STEPS
            or self.config.max_input_bytes != MAX_INPUT_BYTES
            or self.config.budget.max_retries != 0
            or previous_reserved_usd < 0
            or previous_reserved_usd > self.config.budget.max_total_usd
        ):
            raise ValueError("t19_live_budget_contract_mismatch")
        self.open_journal(path, phase_sha256)
        journal = self._ready()
        journal.ledger = replace(journal.ledger, total_spent_usd=previous_reserved_usd)

    def begin_unit(self, unit_id: str) -> None:
        """下一整链最坏费用必须可用；会话和恢复不调用此方法。"""
        self._check_next(MAX_CHAIN_STEPS)
        super().begin_unit(unit_id)

    def begin_replay(self, unit_id: str, prefix_steps: int) -> None:
        """前缀步数占用同一16步上限，前缀不产生新的费用。"""
        if not 0 <= prefix_steps < MAX_CHAIN_STEPS:
            raise ValueError("t19_replay_prefix_out_of_bounds")
        self._check_next(MAX_CHAIN_STEPS - prefix_steps)
        super().begin_unit(unit_id)
        journal = self._ready()
        journal.ledger = replace(journal.ledger, agent_turns=prefix_steps)

    def record_recovery_intent(self, blocked: tuple[str, ...], excluded: tuple[str, ...]) -> None:
        """没有真实阻断来源或当前已响应调用，不能登记恢复。"""
        journal = self._ready()
        if not blocked or not excluded or journal.call is None or journal.received is None:
            raise ValueError("t19_recovery_without_completed_blocked_call")
        intent = RecoveryIntent(
            unit_id=journal.unit_id,
            call=journal.call,
            source_attempt_index=journal.attempt_index,
            next_attempt_index=journal.attempt_index + 1,
            blocked_argument_artifact_ids=blocked,
            excluded_action_ids=excluded,
        )
        path = journal.path.parent / f"recovery-intent-{intent.next_attempt_index:06d}.json"
        with path.open("x", encoding="utf-8") as stream:
            stream.write(intent.model_dump_json() + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    def total_reserved_usd(self) -> Decimal:
        """已结算估算与未知占用之和，不声称提供商已出账。"""
        return self._ready().ledger.total_spent_usd

    def prefix_steps(self, source_unit: str, call_ids: frozenset[str]) -> int:
        """按真实尝试计步，包括失败尝试，不用成功 Decision 数替代。"""
        return sum(
            e.event_type == "attempt"
            and e.unit_id == source_unit
            and e.call is not None
            and e.call.call_id in call_ids
            for e in self._ready().events
        )

    def closed_usage(self) -> UnitUsage:
        """输出累计日志用量用于监督器进度，含所有离线补证调用。"""
        journal = self._ready()
        return summarize_usage(tuple(journal.events), reserved=journal.ledger.total_spent_usd)

    def _check_next(self, remaining_steps: int) -> None:
        journal = self._ready()
        if (
            journal.ledger.total_spent_usd + MAX_CALL_USD * remaining_steps
            > self.config.budget.max_total_usd
        ):
            raise V2BudgetExhaustedError("t19_next_unit_worst_cost")
