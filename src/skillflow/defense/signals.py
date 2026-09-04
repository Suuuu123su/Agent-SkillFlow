"""从请求之前的事件前缀提取可信信号；不读取文本或实验真值。"""

from dataclasses import dataclass
from typing import Literal

from skillflow.defense.models import AttackSignalVector
from skillflow.models.enums import ArtifactType, CapabilityAction, EventType, TrustLevel
from skillflow.models.events import SecurityEvent
from skillflow.models.provenance import Artifact
from skillflow.policy.models import DecisionPlan
from skillflow.policy.runtime import PolicyToolRequest
from skillflow.store.event_store import EventStore, RevocationTargetKind


@dataclass(frozen=True, slots=True)
class SignalProjectionRequest:
    """实际运行身份与当前工具请求；目标选择由预注册效果合同确定。"""

    run_id: str
    request: PolicyToolRequest
    base: DecisionPlan
    risk_target: bool


@dataclass(frozen=True, slots=True)
class SignalProjection:
    """只读证据投影及记忆隔离需要的结构化键和来源。"""

    signals: AttackSignalVector
    memory_key: str | None
    memory_operation: Literal["read", "write"] | None
    memory_untrusted: bool
    memory_artifact_ids: tuple[str, ...]
    prefix_events: tuple[SecurityEvent, ...]


def project_signals(store: EventStore, setup: SignalProjectionRequest) -> SignalProjection:
    """限定到当前请求的前缀，拒绝跨 Run、未来事件和伪造输入引用。"""
    request = setup.request
    argument = store.get_artifact(request.argument_artifact_id)
    event = None if argument is None else store.get_event(argument.created_by_event_id)
    if (
        event is None
        or event.run_id != setup.run_id
        or event.actor_id != request.actor_id
        or event.event_type is not EventType.TOOL_CALL_REQUEST
        or event.call_id != request.boundary.call_id
        or event.session_id != request.boundary.session_id
        or event.requested_effect != request.effect
    ):
        raise ValueError("t18_request_binding")
    all_events = store.iter_run_events(setup.run_id)
    position = next(
        (i for i, item in enumerate(all_events) if item.event_id == event.event_id), None
    )
    if position is None:
        raise ValueError("t18_request_binding")
    prefix = all_events[: position + 1]
    key, operation = _memory_request(setup)
    roots = tuple(a.artifact_id for a in request.source_artifacts)
    roots = tuple(dict.fromkeys((*roots, *request.text_claim_artifact_ids)))
    memory_head = _memory_root(prefix, key) if operation == "read" else None
    if memory_head is not None:
        roots = tuple(dict.fromkeys((*roots, memory_head)))
    artifacts, complete = _ancestors(store, prefix, roots)
    by_event = {item.event_id: item for item in prefix}
    actors = {by_event[a.created_by_event_id].actor_id for a in artifacts}
    origins = {o for a in artifacts for o in a.observed_label.origins}
    revocations = tuple(
        r
        for r in store.iter_run_revocations(setup.run_id)
        if r.event_id in by_event
        and r.target_kind is RevocationTargetKind.PRINCIPAL
        and r.target_id in actors | origins
    )
    untrusted = tuple(
        a for a in artifacts if a.observed_label.trust in {TrustLevel.UNTRUSTED, TrustLevel.UNKNOWN}
    )
    untrusted_ids = {a.artifact_id for a in untrusted}
    context = tuple(
        a for a in untrusted if a.artifact_type in {ArtifactType.CONTEXT, ArtifactType.SKILL_OUTPUT}
    )
    returns = tuple(
        item
        for item in prefix
        if item.event_type is EventType.TOOL_CALL_RESULT
        and untrusted_ids.intersection(item.input_artifact_ids)
    )
    memories = tuple(a for a in artifacts if a.artifact_type is ArtifactType.MEMORY)
    cross = bool(memories) and any(
        a.observed_label.created_session_id != event.session_id for a in artifacts
    )
    revoked = bool(revocations) or any(a.observed_label.revoked_origins for a in artifacts)
    reasons = set(setup.base.reason_codes)
    signal_evidence = {
        "untrusted_context_in_basis": tuple(a.artifact_id for a in context),
        "untrusted_tool_return_in_basis": tuple(e.event_id for e in returns),
        "cross_session_memory_path": tuple(a.artifact_id for a in memories) if cross else (),
        "revoked_origin": tuple(r.event_id for r in revocations),
        "authorization_claim_in_basis": request.text_claim_artifact_ids,
    }
    evidence = tuple(
        dict.fromkeys(
            (
                event.event_id,
                *(a.artifact_id for a in artifacts),
                *(a.created_by_event_id for a in artifacts),
                *(r.event_id for r in revocations),
                *(e.event_id for e in returns),
                *setup.base.matched_grant_ids,
            )
        )
    )
    signals = AttackSignalVector(
        run_id=setup.run_id,
        session_id=event.session_id,
        request_event_id=event.event_id,
        grant_missing=not bool(setup.base.matched_grant_ids),
        scope_mismatch=bool(reasons & {"RESOURCE_SCOPE_EXCEEDED", "SINK_SCOPE_EXCEEDED"}),
        lifetime_mismatch=bool(
            reasons
            & {
                "CROSS_CALL_USE",
                "CROSS_TASK_USE",
                "CROSS_SESSION_USE",
                "GRANT_EXPIRED",
                "GRANT_NOT_YET_VALID",
            }
        ),
        revoked_origin=revoked,
        untrusted_context_in_basis=bool(context),
        untrusted_tool_return_in_basis=bool(returns),
        cross_session_memory_path=cross,
        authorization_claim_in_basis=bool(request.text_claim_artifact_ids),
        candidate_influence=bool(untrusted) or revoked or cross,
        confirmed_influence=False,
        target_effect_requested=setup.risk_target,
        target_effect_executed=False,
        receipt_present=False,
        sink_severity=request.effect.sensitivity,
        evidence_availability={
            "authorization": setup.base.manifest_id is not None,
            "provenance": complete,
        },
        evidence_ids=evidence,
        signal_evidence=signal_evidence,
    )
    return SignalProjection(
        signals, key, operation, bool(untrusted), tuple(a.artifact_id for a in artifacts), prefix
    )


def _memory_request(
    setup: SignalProjectionRequest,
) -> tuple[str | None, Literal["read", "write"] | None]:
    effect = setup.request.effect
    if effect.action is CapabilityAction.MEMORY_WRITE:
        return effect.sink.root.removeprefix("memory:/"), "write"
    if effect.action is CapabilityAction.MEMORY_READ and effect.source is not None:
        return effect.source.root.removeprefix("memory:/"), "read"
    return None, None


def _memory_root(events: tuple[SecurityEvent, ...], key: str | None) -> str | None:
    for event in reversed(events):
        if event.metadata.get("memory_key") != key or key is None:
            continue
        if event.event_type is EventType.MEMORY_DELETE:
            return None
        if event.event_type is EventType.MEMORY_WRITE:
            return next(iter(event.output_artifact_ids), None)
    return None


def _ancestors(
    store: EventStore, events: tuple[SecurityEvent, ...], roots: tuple[str, ...]
) -> tuple[tuple[Artifact, ...], bool]:
    by_event = {event.event_id: event for event in events}
    seen: set[str] = set()
    pending = list(roots)
    artifacts = []
    complete = True
    while pending:
        identifier = pending.pop()
        if identifier in seen:
            continue
        seen.add(identifier)
        artifact = store.get_artifact(identifier)
        if artifact is None or artifact.created_by_event_id not in by_event:
            raise ValueError("t18_source_artifact_prefix_binding")
        complete = complete and bool(artifact.observed_label.origins)
        event = by_event[artifact.created_by_event_id]
        if identifier not in event.output_artifact_ids:
            raise ValueError("t18_source_artifact_producer_binding")
        artifacts.append(artifact)
        pending.extend(event.input_artifact_ids)
    return tuple(sorted(artifacts, key=lambda a: a.artifact_id)), complete
