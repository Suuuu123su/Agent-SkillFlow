from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final

from skillflow.models.effects import CapabilityEffect, EffectRecord
from skillflow.models.enums import (
    ArtifactType,
    CapabilityAction,
    Decision,
    EnforcementMode,
    EventType,
    Lifetime,
    TrustLevel,
)
from skillflow.models.events import DecisionRecord
from skillflow.models.resources import ResourceRef
from skillflow.runtime.determinism import DeterministicIdFactory, VirtualClock
from skillflow.runtime.session import (
    ActorCall,
    ArtifactEmission,
    EventEmission,
    RuntimeDependencies,
    RuntimeRecorder,
    SessionIdentity,
)
from skillflow.store.blob_store import RunBlobStore
from skillflow.store.sqlite_store import SqliteEventStore

PAYLOAD_MARKER: Final = "T07_GOLDEN_PAYLOAD"
RUN_ID: Final = "run-t07-golden"


@dataclass(frozen=True, slots=True)
class GoldenGraphIds:
    database_path: Path
    run_id: str
    effect_id: str
    grant_id: str
    skill_a_output_id: str
    memory_id: str
    context_id: str
    tool_argument_id: str
    skill_a_id: str
    skill_b_id: str
    tool_id: str
    causal_event_ids: tuple[str, ...]
    grant_event_id: str
    revoke_event_id: str
    cycle_event_id: str | None


def build_golden_store(root: Path, *, include_cycle: bool = False) -> GoldenGraphIds:
    database = root / "state.sqlite"
    clock = VirtualClock(datetime(2026, 1, 1, tzinfo=UTC))
    ids = DeterministicIdFactory("t07-golden")
    skill_a_id = "skill-a"
    skill_b_id = "skill-b"
    tool_id = "tool:http_send"
    grant_id = "grant-network-send"

    with SqliteEventStore(database) as store, RunBlobStore(root, RUN_ID) as blobs:
        dependencies = RuntimeDependencies(store, blobs, clock, ids)
        first = RuntimeRecorder(
            SessionIdentity(RUN_ID, "task-t07", "session-1"),
            dependencies,
        )
        skill_a_output = first.record_artifact(
            ArtifactEmission(
                event_type=EventType.SKILL_RETURN,
                artifact_type=ArtifactType.SKILL_OUTPUT,
                content=PAYLOAD_MARKER.encode(),
                actor=ActorCall(skill_a_id, "call-a"),
                origins=frozenset({skill_a_id}),
                trust=TrustLevel.UNTRUSTED,
                mime_type="text/plain",
                metadata={"skill_id": skill_a_id, "secret": PAYLOAD_MARKER},
            )
        )
        cycle_event_id: str | None = None
        if include_cycle:
            cycle_event_id = first.record_event(
                EventEmission(
                    event_type=EventType.SKILL_INVOKE,
                    actor=ActorCall(skill_a_id, "call-cycle"),
                    input_artifact_ids=(skill_a_output.artifact_id,),
                    metadata={"skill_id": skill_a_id},
                )
            ).event_id
        memory = first.record_artifact(
            ArtifactEmission(
                event_type=EventType.MEMORY_WRITE,
                artifact_type=ArtifactType.MEMORY,
                content=PAYLOAD_MARKER.encode(),
                actor=ActorCall(skill_a_id, "call-a"),
                input_artifact_ids=(skill_a_output.artifact_id,),
                origins=frozenset({skill_a_id}),
                trust=TrustLevel.UNTRUSTED,
                mime_type="text/plain",
                metadata={"memory_key": "shared"},
            )
        )
        clock.advance(timedelta(seconds=1))
        revoke_event = first.record_event(
            EventEmission(
                event_type=EventType.SKILL_REVOKE,
                actor=ActorCall("user", None),
                metadata={"skill_id": skill_a_id},
            )
        )

        second = RuntimeRecorder(
            SessionIdentity(RUN_ID, "task-t07", "session-2"),
            dependencies,
        )
        context = second.record_artifact(
            ArtifactEmission(
                event_type=EventType.MEMORY_READ,
                artifact_type=ArtifactType.CONTEXT,
                content=PAYLOAD_MARKER.encode(),
                actor=ActorCall(skill_b_id, "call-b"),
                input_artifact_ids=(memory.artifact_id,),
                origins=frozenset({skill_a_id}),
                trust=TrustLevel.UNTRUSTED,
                mime_type="text/plain",
                metadata={"memory_key": "shared"},
            )
        )
        invoke_event = second.record_event(
            EventEmission(
                event_type=EventType.SKILL_INVOKE,
                actor=ActorCall(skill_b_id, "call-b"),
                input_artifact_ids=(context.artifact_id,),
                metadata={"skill_id": skill_b_id},
            )
        )
        skill_b_output = second.record_artifact(
            ArtifactEmission(
                event_type=EventType.SKILL_RETURN,
                artifact_type=ArtifactType.SKILL_OUTPUT,
                content=PAYLOAD_MARKER.encode(),
                actor=ActorCall(skill_b_id, "call-b"),
                input_artifact_ids=(context.artifact_id,),
                origins=frozenset({skill_a_id, skill_b_id}),
                trust=TrustLevel.UNTRUSTED,
                mime_type="text/plain",
                metadata={"skill_id": skill_b_id},
            )
        )
        grant_event = second.record_event(
            EventEmission(
                event_type=EventType.AUTH_GRANT,
                actor=ActorCall("user", None),
                metadata={"grant_id": grant_id, "secret": PAYLOAD_MARKER},
            )
        )
        effect_value = CapabilityEffect(
            source=ResourceRef("context:/task"),
            action=CapabilityAction.NETWORK_SEND,
            sink=ResourceRef("mock://external"),
            scope="exact-sink",
            lifetime=Lifetime.CALL,
            sensitivity=2,
        )
        tool_argument = second.record_artifact(
            ArtifactEmission(
                event_type=EventType.TOOL_CALL_REQUEST,
                artifact_type=ArtifactType.TOOL_ARG,
                content=PAYLOAD_MARKER.encode(),
                actor=ActorCall(skill_b_id, "call-b"),
                input_artifact_ids=(skill_b_output.artifact_id,),
                origins=frozenset({skill_a_id, skill_b_id}),
                trust=TrustLevel.UNTRUSTED,
                mime_type="application/json",
                requested_effect=effect_value,
                metadata={"tool": "http_send", "secret": PAYLOAD_MARKER},
            )
        )
        result_ids = second.allocate_artifact_ids()
        decision_id = second.new_id("decision")
        effect_id = second.new_id("effect")
        decision = DecisionRecord(
            decision_id=decision_id,
            request_event_id=tool_argument.created_by_event_id,
            enforcement_mode=EnforcementMode.MONITOR,
            baseline_result=Decision.ALLOW,
            policy_result=Decision.ALLOW,
            authorized=True,
            executed=True,
            matched_grant_ids=(grant_id,),
            reason_codes=("golden_fixture",),
        )
        effect = EffectRecord(
            effect_id=effect_id,
            effect=effect_value,
            request_event_id=tool_argument.created_by_event_id,
            decision_id=decision_id,
            result_event_id=result_ids.event_id,
            tool_receipt_id="receipt-golden",
            executed=True,
        )
        receipt = second.record_prepared_artifact(
            result_ids,
            ArtifactEmission(
                event_type=EventType.TOOL_CALL_RESULT,
                artifact_type=ArtifactType.TOOL_RETURN,
                content=PAYLOAD_MARKER.encode(),
                actor=ActorCall(tool_id, "call-b"),
                input_artifact_ids=(tool_argument.artifact_id,),
                origins=frozenset({skill_b_id}),
                trust=TrustLevel.TRUSTED,
                mime_type="application/json",
                requested_effect=effect_value,
                decision_id=decision_id,
                decision=decision,
                effect=effect,
                metadata={"tool": "http_send", "secret": PAYLOAD_MARKER},
            ),
        )

    return GoldenGraphIds(
        database_path=database,
        run_id=RUN_ID,
        effect_id=effect_id,
        grant_id=grant_id,
        skill_a_output_id=skill_a_output.artifact_id,
        memory_id=memory.artifact_id,
        context_id=context.artifact_id,
        tool_argument_id=tool_argument.artifact_id,
        skill_a_id=skill_a_id,
        skill_b_id=skill_b_id,
        tool_id=tool_id,
        causal_event_ids=(
            skill_a_output.created_by_event_id,
            memory.created_by_event_id,
            context.created_by_event_id,
            invoke_event.event_id,
            skill_b_output.created_by_event_id,
            tool_argument.created_by_event_id,
            receipt.created_by_event_id,
        ),
        grant_event_id=grant_event.event_id,
        revoke_event_id=revoke_event.event_id,
        cycle_event_id=cycle_event_id,
    )
