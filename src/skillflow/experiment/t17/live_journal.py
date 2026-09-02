"""T17 Live 调用前预算与逐响应实际用量的哈希链日志。"""

import hashlib
import json
import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic_core import to_jsonable_python

from skillflow.experiment.t16.budget import BudgetLedger
from skillflow.experiment.t16.live_agent_calls import ActualResponseUsage
from skillflow.experiment.t16.live_record_builders import add_usage, zero_usage
from skillflow.experiment.t16.provider import TokenUsage
from skillflow.experiment.t17.live_attempt_models import (
    T17LiveUnitKind,
)
from skillflow.experiment.t17.live_journal_models import (
    T17JournalTerminal,
    T17LiveJournalBinding,
    T17LiveJournalError,
    T17LiveJournalErrorCode,
    T17LiveJournalEvent,
    T17ModelRevisionDriftError,
    journal_usage_status,
)
from skillflow.experiment.t17.live_reference_client import ReferenceLiveTelemetry


class T17LiveUsageJournal:
    """每次网络调用前 fsync，并对所有事件建立 SHA-256 链。"""

    def __init__(
        self,
        path: Path,
        binding: T17LiveJournalBinding,
    ) -> None:
        """绑定日志路径、阶段合同和冻结模型身份。"""
        self.path = path
        self.binding = binding
        self._events: list[T17LiveJournalEvent] = []
        self._terminal_units: set[str] = set()
        self._opened = False

    def open_new(self) -> None:
        """独占新建日志；拒绝覆盖任何旧 Attempt。"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self.path.open("x", encoding="utf-8", newline="\n") as stream:
                stream.flush()
                os.fsync(stream.fileno())
        except OSError as error:
            raise T17LiveJournalError(
                T17LiveJournalErrorCode.OPEN_FAILED,
                self.path.name,
            ) from error
        self._opened = True

    def start_unit(
        self,
        unit_id: str,
        trial_id: str,
        unit_kind: T17LiveUnitKind,
    ) -> "T17LiveUsageTracker":
        """为一个核心 Run 或 Replay pair 创建私有累计器。"""
        if not self._opened:
            raise T17LiveJournalError(T17LiveJournalErrorCode.NOT_OPEN)
        if unit_id in self._terminal_units:
            raise T17LiveJournalError(
                T17LiveJournalErrorCode.UNIT_TERMINAL,
                unit_id,
            )
        return T17LiveUsageTracker(self, unit_id, trial_id, unit_kind)

    def append(self, payload: dict[str, object]) -> T17LiveJournalEvent:
        """补齐序号和链哈希，验证后追加并 fsync。"""
        if not self._opened:
            raise T17LiveJournalError(T17LiveJournalErrorCode.NOT_OPEN)
        sequence = len(self._events) + 1
        previous = None if not self._events else self._events[-1].event_sha256
        base = {
            **payload,
            "schema_version": "0.1",
            "sequence": sequence,
            "phase_contract_sha256": self.binding.phase_contract_sha256,
            "approved_config_sha256": self.binding.approved_config_sha256,
            "stage": self.binding.stage,
            "provider": "openai",
            "expected_model_id": self.binding.model_id,
            "expected_model_revision": self.binding.model_revision,
            "previous_event_sha256": previous,
        }
        digest = _event_sha256(base)
        event = T17LiveJournalEvent.model_validate({**base, "event_sha256": digest})
        try:
            with self.path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(event.model_dump_json())
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
        except OSError as error:
            raise T17LiveJournalError(T17LiveJournalErrorCode.APPEND_FAILED) from error
        self._events.append(event)
        if event.event_type == "terminal":
            self._terminal_units.add(event.unit_id)
        return event


@dataclass(slots=True)
class T17LiveUsageTracker:
    """一条调度单元的调用、响应、费用与模型 revision 累计器。"""

    journal: T17LiveUsageJournal
    unit_id: str
    trial_id: str
    unit_kind: T17LiveUnitKind
    api_call_count: int = 0
    response_count: int = 0
    total_reserved_usd: Decimal = Decimal(0)
    run_reserved_usd: Decimal = Decimal(0)
    token_usage: TokenUsage | None = None
    estimated_cost_usd: Decimal | None = None
    actual_model_revision: str | None = None
    _finalized: bool = False

    def record_attempt(self, budget: BudgetLedger) -> None:
        """在 Client I/O 前保存最新保守预留。"""
        self._require_active()
        self.api_call_count += 1
        self.total_reserved_usd = budget.total_spent_usd
        self.run_reserved_usd = budget.run_spent_usd
        self.journal.append(self._payload("attempt"))

    def record_response(self, usage: TokenUsage, estimated_cost_usd: Decimal) -> None:
        """兼容不提供 Provider 元数据的调用边界。"""
        self._record_response(
            usage,
            estimated_cost_usd,
            self.journal.binding.model_revision,
            None,
        )

    def record_detailed_response(self, response: ActualResponseUsage) -> None:
        """响应返回即累计并保存实际 Provider/model 元数据。"""
        self._record_response(
            response.token_usage,
            response.estimated_cost_usd,
            response.model_revision,
            response.budget,
        )
        if response.model_id != self.journal.binding.model_id:
            raise T17ModelRevisionDriftError(
                self.journal.binding.model_id,
                response.model_id,
            )
        if response.model_revision != self.journal.binding.model_revision:
            raise T17ModelRevisionDriftError(
                self.journal.binding.model_revision,
                response.model_revision,
            )

    def finalize(
        self,
        telemetry: ReferenceLiveTelemetry,
        terminal: T17JournalTerminal,
    ) -> ReferenceLiveTelemetry:
        """写入终态，并返回由即时日志收紧后的单元遥测。"""
        self._require_active()
        observed = telemetry.model_copy(
            update={
                "api_call_count": self.api_call_count,
                "response_count": self.response_count,
                "token_usage": self.token_usage or zero_usage(),
                "estimated_cost_usd": self.estimated_cost_usd or Decimal(0),
                "conservative_reserved_usd": self.run_reserved_usd,
            }
        )
        self.journal.append(
            self._payload(
                "terminal",
                telemetry=observed,
                terminal=terminal,
            )
        )
        self._finalized = True
        return observed

    def _record_response(
        self,
        usage: TokenUsage,
        cost: Decimal,
        model_revision: str,
        budget: BudgetLedger | None,
    ) -> None:
        self._require_active()
        self.response_count += 1
        self.token_usage = usage if self.token_usage is None else add_usage(self.token_usage, usage)
        self.estimated_cost_usd = (
            cost if self.estimated_cost_usd is None else (self.estimated_cost_usd + cost)
        )
        self.actual_model_revision = model_revision
        if budget is not None:
            self.total_reserved_usd = budget.total_spent_usd
            self.run_reserved_usd = budget.run_spent_usd
        self.journal.append(self._payload("response"))

    def _payload(
        self,
        event_type: Literal["attempt", "response", "terminal"],
        *,
        telemetry: ReferenceLiveTelemetry | None = None,
        terminal: T17JournalTerminal | None = None,
    ) -> dict[str, object]:
        return {
            "event_type": event_type,
            "unit_id": self.unit_id,
            "trial_id": self.trial_id,
            "unit_kind": self.unit_kind,
            "api_call_count": self.api_call_count,
            "response_count": self.response_count,
            "total_reserved_usd": self.total_reserved_usd,
            "run_reserved_usd": self.run_reserved_usd,
            "actual_usage_status": journal_usage_status(
                self.api_call_count,
                self.response_count,
            ),
            "observed_token_usage": self.token_usage,
            "observed_estimated_cost_usd": self.estimated_cost_usd,
            "actual_model_revision": (
                None if event_type == "attempt" else self.actual_model_revision
            ),
            "latency_ms": 0 if telemetry is None else telemetry.latency_ms,
            "agent_step_count": (0 if telemetry is None else telemetry.agent_step_count),
            "retry_count": 0 if telemetry is None else telemetry.retry_count,
            "refusal_count": 0 if telemetry is None else telemetry.refusal_count,
            "no_call_count": 0 if telemetry is None else telemetry.no_call_count,
            "terminal_status": None if terminal is None else terminal.status,
            "failure_kind": (None if terminal is None else terminal.failure_kind),
            "failure_detail": (None if terminal is None else terminal.failure_detail),
            "failure_diagnostic": (None if terminal is None else terminal.failure_diagnostic),
        }

    def _require_active(self) -> None:
        if self._finalized:
            raise T17LiveJournalError(
                T17LiveJournalErrorCode.UNIT_FINALIZED,
                self.unit_id,
            )


def load_live_journal(path: Path) -> tuple[T17LiveJournalEvent, ...]:
    """严格验证 sequence、前向哈希和每条事件哈希。"""
    try:
        lines = tuple(line for line in path.read_text(encoding="utf-8").splitlines() if line)
    except OSError as error:
        raise T17LiveJournalError(
            T17LiveJournalErrorCode.READ_FAILED,
            path.name,
        ) from error
    raw_events = tuple(json.loads(line) for line in lines)
    events = tuple(T17LiveJournalEvent.model_validate(item) for item in raw_events)
    previous: str | None = None
    for expected_sequence, (event, raw) in enumerate(
        zip(events, raw_events, strict=True),
        start=1,
    ):
        if event.sequence != expected_sequence or event.previous_event_sha256 != previous:
            raise T17LiveJournalError(T17LiveJournalErrorCode.CHAIN_INVALID)
        payload = {key: value for key, value in raw.items() if key != "event_sha256"}
        if _event_sha256(payload) != event.event_sha256:
            raise T17LiveJournalError(T17LiveJournalErrorCode.HASH_INVALID)
        previous = event.event_sha256
    return events


def _event_sha256(payload: dict[str, object]) -> str:
    normalized = to_jsonable_python(payload)
    encoded = json.dumps(
        normalized,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
