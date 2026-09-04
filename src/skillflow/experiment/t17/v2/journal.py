"""逐次同步落盘的 API 用量哈希链，持久化不等待任务终态。"""

import hashlib
import json
import os
from decimal import Decimal
from pathlib import Path

from skillflow.experiment.t16.budget import BudgetLedger
from skillflow.experiment.t16.live_agent_calls import ActualResponseUsage
from skillflow.experiment.t16.provider import TokenUsage
from skillflow.experiment.t17.v2.api_models import (
    ApiUsageEvent,
    CallIdentity,
    V2LiveConfig,
    V2UsageWriteFailureError,
)
from skillflow.experiment.t17.v2.journal_order import JournalOrder
from skillflow.experiment.t17.v2.run_models import UnitUsage
from skillflow.experiment.t17.v2.usage_summary import summarize_usage


class V2UsageJournal:
    """一条尝试一份新日志；错误请求的保守占用不会被下一条抹掉。"""

    def __init__(self, path: Path, config: V2LiveConfig, phase_sha256: str) -> None:
        """先独占创建并同步文件，成功后才能授权请求。"""
        self.path, self.config, self.phase_sha256 = path, config, phase_sha256
        self.events: list[ApiUsageEvent] = []
        self.ledger = BudgetLedger(config.budget)
        self.unit_id = "unbound"
        self.call: CallIdentity | None = None
        self.attempt_index = 0
        self.received: ApiUsageEvent | None = None
        self._seen_units: set[str] = set()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.flush()
            os.fsync(stream.fileno())

    def begin_unit(self, unit_id: str) -> None:
        """只重置本单元，保留全阶段的已用和失败请求占用。"""
        if unit_id in self._seen_units:
            raise ValueError("v2_journal_unit_already_started")
        self._seen_units.add(unit_id)
        self.unit_id, self.call, self.received = unit_id, None, None
        self.ledger = self.ledger.begin_run()
        self.append("unit_start")

    def append(self, kind: str, **fields: object) -> ApiUsageEvent:
        """不接收自由文本请求或响应字段；全部数据经过封闭模型检查。"""
        event = ApiUsageEvent.model_validate(
            {
                "sequence": len(self.events) + 1,
                "event_type": kind,
                "phase_contract_sha256": self.phase_sha256,
                "matrix_sha256": self.config.matrix_sha256,
                "unit_id": self.unit_id,
                "call": self.call,
                "attempt_index": self.attempt_index,
                "total_reserved_usd": self.ledger.total_spent_usd,
                "unit_reserved_usd": self.ledger.run_spent_usd,
                "previous_sha256": None if not self.events else self.events[-1].event_sha256,
                "event_sha256": "0" * 64,
                **fields,
            }
        )
        event = event.model_copy(update={"event_sha256": _hash_event(event)})
        try:
            with self.path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(event.model_dump_json() + "\n")
                stream.flush()
                os.fsync(stream.fileno())
        except OSError as error:
            raise V2UsageWriteFailureError("v2_usage_fsync_failed") from error
        self.events.append(event)
        return event

    def record_attempt(self, budget: BudgetLedger) -> None:
        """在实际网络调用前同步保存一次预留；写入失败则根本不调用。"""
        self.attempt_index += 1
        self.received = None
        self.ledger = budget
        self.append("attempt")

    def record_response(self, usage: TokenUsage, estimated_cost_usd: Decimal) -> None:
        """禁止缺少即时 HTTP 头记录的旧式回退路径。"""
        del usage, estimated_cost_usd
        raise V2UsageWriteFailureError("v2_detailed_response_required")

    def record_detailed_response(self, response: ActualResponseUsage) -> None:
        """核对解析前后用量相同，再持久化结算后的预算。"""
        received = self.received
        if (
            received is None
            or received.usage != response.token_usage
            or received.estimated_cost_usd != response.estimated_cost_usd
        ):
            raise V2UsageWriteFailureError("v2_response_accounting_mismatch")
        if response.budget is not None:
            self.ledger = response.budget
        self.append("settlement")

    def usage(self) -> UnitUsage:
        """仅由当前单元的持久行计算 Token、延迟与实际估算费用。"""
        rows = tuple(e for e in self.events if e.unit_id == self.unit_id)
        return summarize_usage(rows, reserved=self.ledger.run_spent_usd)


def _hash_event(event: ApiUsageEvent) -> str:
    value = json.dumps(
        event.model_dump(mode="json", exclude={"event_sha256"}),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(value.encode()).hexdigest()


def read_journal(
    path: Path, *, allowed_phases: frozenset[str] = frozenset()
) -> tuple[ApiUsageEvent, ...]:
    """离线复核顺序、哈希链和响应对应的真实调用。"""
    events = tuple(
        ApiUsageEvent.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
    )
    return verify_journal(events, allowed_phases=allowed_phases)


def verify_journal(
    events: tuple[ApiUsageEvent, ...], *, allowed_phases: frozenset[str] = frozenset()
) -> tuple[ApiUsageEvent, ...]:
    """标准数据集复用同一哈希链校验，不需要读取原始响应正文。"""
    previous = None
    order = JournalOrder()
    seen_responses: set[str] = set()
    for sequence, event in enumerate(events, 1):
        if (
            event.sequence != sequence
            or event.previous_sha256 != previous
            or event.event_sha256 != _hash_event(event)
        ):
            raise ValueError("v2_usage_journal_hash_chain")
        previous = event.event_sha256
        if (
            event.phase_contract_sha256 not in (allowed_phases or {events[0].phase_contract_sha256})
            or event.matrix_sha256 != events[0].matrix_sha256
        ):
            raise ValueError("v2_usage_journal_phase_drift")
        order.accept(event)
        if event.event_type == "response":
            if event.response_id in seen_responses:
                raise ValueError("v2_usage_response_attempt_binding")
            if event.response_id is not None:
                seen_responses.add(event.response_id)
    return events
