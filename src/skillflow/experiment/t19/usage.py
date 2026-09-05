"""T19 恢复感知的账本校验；哈希、结算、身份与禁止重采规则仍保留。"""

from dataclasses import dataclass, field
from pathlib import Path

from skillflow.experiment.t17.v2.api_models import ApiUsageEvent
from skillflow.experiment.t17.v2.journal import _hash_event
from skillflow.experiment.t17.v2.journal_order import JournalOrder
from skillflow.experiment.t19.continuation import RecoveryIntent
from skillflow.experiment.t19.execution import CoreRecord

RECOVERY_DECISION_COUNT = 2


@dataclass(slots=True)
class _RecoveryOrder(JournalOrder):
    recovery_attempts: frozenset[int] = field(default_factory=frozenset)

    def _attempt(self, event: ApiUsageEvent) -> None:
        if event.attempt_index not in self.recovery_attempts:
            super(_RecoveryOrder, self)._attempt(event)
            return
        if event.attempt_index != len(self.attempts) + 1 or not self._closed():
            raise ValueError("t19_recovery_attempt_order")
        self.attempts[event.attempt_index] = event


def read_usage(path: Path, live_root: Path) -> tuple[ApiUsageEvent, ...]:
    """恢复必须有事前意图，旧预检仅接受已闭合事实证明的单次恢复。"""
    rows = tuple(
        ApiUsageEvent.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
    )
    attempts = {e.attempt_index: e for e in rows if e.event_type == "attempt"}
    allowed: set[int] = set()
    for file in path.parent.glob("recovery-intent-*.json"):
        intent = RecoveryIntent.model_validate_json(file.read_text(encoding="utf-8"))
        before = attempts.get(intent.source_attempt_index)
        after = attempts.get(intent.next_attempt_index)
        if after is None:
            continue  # 请求前预算门可以阻止已经登记的恢复，不能据此虚构调用。
        if (
            before is None
            or before.call != intent.call
            or after.call != intent.call
            or before.unit_id != intent.unit_id
            or after.unit_id != intent.unit_id
            or intent.next_attempt_index != intent.source_attempt_index + 1
            or not intent.blocked_argument_artifact_ids
            or not intent.excluded_action_ids
        ):
            raise ValueError("t19_recovery_intent_binding")
        allowed.add(after.attempt_index)
    # v1 was emitted before recovery intents existed. No runtime retry exception is added.
    if path.parent.name == "precheck-01":
        allowed.update(_legacy_closed_recoveries(attempts, live_root / "precheck-v1/core"))
    order = _RecoveryOrder(recovery_attempts=frozenset(allowed))
    previous = None
    responses: set[str] = set()
    for sequence, event in enumerate(rows, start=1):
        if (
            event.sequence != sequence
            or event.previous_sha256 != previous
            or event.event_sha256 != _hash_event(event)
        ):
            raise ValueError("t19_usage_hash_chain")
        if (
            event.phase_contract_sha256 != rows[0].phase_contract_sha256
            or event.matrix_sha256 != rows[0].matrix_sha256
        ):
            raise ValueError("t19_usage_phase_binding")
        order.accept(event)
        previous = event.event_sha256
        if event.response_id is not None:
            if event.response_id in responses:
                raise ValueError("t19_duplicate_provider_response")
            responses.add(event.response_id)
    return rows


def _legacy_closed_recoveries(attempts: dict[int, ApiUsageEvent], directory: Path) -> set[int]:
    allowed: set[int] = set()
    for path in directory.glob("*.json"):
        core = CoreRecord.model_validate_json(path.read_text(encoding="utf-8"))
        events = {e.event_id: e for e in core.data.facts.events}
        for recovery in core.recoveries:
            decisions = tuple(d for d in core.decisions if d.call_id == recovery.call_id)
            calls = tuple(
                a
                for a in attempts.values()
                if a.unit_id == core.unit_id
                and a.call is not None
                and a.call.call_id == recovery.call_id
            )
            if (
                len(decisions) != RECOVERY_DECISION_COUNT
                or len(calls) != RECOVERY_DECISION_COUNT
                or recovery.additional_model_decisions != 1
                or decisions[0].behavior != "normal"
                or set(decisions[1].allowed_action_ids)
                != set(decisions[0].allowed_action_ids) - set(recovery.excluded_action_ids)
                or not recovery.blocked_action_ids
                or not any(
                    not d.executed and events[d.request_event_id].call_id == recovery.call_id
                    for d in core.data.facts.decisions
                )
            ):
                raise ValueError("t19_legacy_recovery_not_proven")
            allowed.add(calls[1].attempt_index)
    return allowed
