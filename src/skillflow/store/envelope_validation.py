"""EventEnvelope 跨事实引用的一致性校验。"""

from typing import assert_never

from skillflow.models.enums import EventType
from skillflow.models.events import SecurityEvent
from skillflow.store.errors import StoreIntegrityError
from skillflow.store.event_store import EventEnvelope, RevocationRecord, RevocationTargetKind


def validate_envelope(envelope: EventEnvelope) -> None:
    """在事务开始前拒绝引用不一致的组合事实。"""
    event = envelope.event
    decision = envelope.decision
    effect = envelope.effect
    grant = envelope.grant
    revocation = envelope.revocation
    if decision is not None and event.decision_id != decision.decision_id:
        raise StoreIntegrityError("append_event", "Decision 与 Event 引用不一致")
    if (
        decision is not None
        and effect is not None
        and decision.request_event_id != effect.request_event_id
    ):
        raise StoreIntegrityError("append_event", "Decision 与 Effect 的请求引用不一致")
    if effect is not None and effect.result_event_id is None:
        if effect.request_event_id != event.event_id:
            raise StoreIntegrityError("append_event", "Effect 与请求 Event 引用不一致")
    elif effect is not None and effect.result_event_id != event.event_id:
        raise StoreIntegrityError("append_event", "Effect 与结果 Event 引用不一致")
    if effect is not None and effect.decision_id != event.decision_id:
        raise StoreIntegrityError("append_event", "Effect 与 Event 的 Decision 引用不一致")
    if effect is not None and effect.effect != event.requested_effect:
        raise StoreIntegrityError("append_event", "Effect 与 Event 请求的能力不一致")
    if grant is not None and (
        event.event_type is not EventType.AUTH_GRANT
        or event.actor_id != grant.issuer_id
        or event.metadata.get("grant_id") != grant.grant_id
    ):
        raise StoreIntegrityError("append_event", "Grant 与 AUTH_GRANT Event 不一致")
    if revocation is not None:
        _validate_revocation(event, revocation)


def _validate_revocation(event: SecurityEvent, revocation: RevocationRecord) -> None:
    if event.event_id != revocation.event_id or event.timestamp != revocation.timestamp:
        raise StoreIntegrityError("append_event", "Revocation 与 Event 时间或 ID 不一致")
    match revocation.target_kind:
        case RevocationTargetKind.GRANT:
            valid = (
                event.event_type is EventType.AUTH_REVOKE
                and event.metadata.get("grant_id") == revocation.target_id
            )
        case RevocationTargetKind.PRINCIPAL:
            valid = (
                event.event_type is EventType.SKILL_REVOKE
                and event.metadata.get("skill_id") == revocation.target_id
            )
        case _ as unreachable:
            assert_never(unreachable)
    if not valid:
        raise StoreIntegrityError("append_event", "Revocation 与撤销 Event 不一致")
