"""EventStore 与 BlobStore 的逻辑 checkpoint 导入导出。"""

from dataclasses import dataclass

from skillflow.models.authorization import AuthorizationGrant
from skillflow.models.enums import EventType
from skillflow.models.events import SecurityEvent
from skillflow.models.provenance import Artifact
from skillflow.store.blob_store import RunBlobStore
from skillflow.store.errors import StoreIntegrityError
from skillflow.store.event_store import (
    EventEnvelope,
    EventStore,
    MemoryHead,
    StoredArtifact,
)


@dataclass(frozen=True, slots=True)
class ArtifactSnapshot:
    """Artifact 元数据与只在 checkpoint 内部使用的内容。"""

    artifact: Artifact
    content: bytes


@dataclass(frozen=True, slots=True)
class RunStoreSnapshot:
    """一个 Run 在 step 边界的完整追加前缀与 Memory 头。"""

    envelopes: tuple[EventEnvelope, ...]
    artifacts: tuple[ArtifactSnapshot, ...]
    memory_heads: tuple[MemoryHead, ...]


@dataclass(frozen=True, slots=True)
class StoreCaptureRequest:
    """逻辑导出所需的 Run 与存储资源。"""

    run_id: str
    event_store: EventStore
    blob_store: RunBlobStore
    memory_entries: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class StoreRestoreSetup:
    """逻辑导入所需的全新分支资源。"""

    target_run_id: str
    event_store: EventStore
    blob_store: RunBlobStore


def capture_run_store(request: StoreCaptureRequest) -> RunStoreSnapshot:
    """通过公开 Store 合同冻结一个 Run 的有序事实。"""
    request.blob_store.flush()
    request.event_store.flush()
    events = request.event_store.iter_run_events(request.run_id)
    effects = {
        (
            effect.result_event_id
            if effect.result_event_id is not None
            else effect.request_event_id
        ): effect
        for effect in request.event_store.iter_run_effects(request.run_id)
    }
    revocations = {
        revocation.event_id: revocation
        for revocation in request.event_store.iter_run_revocations(request.run_id)
    }
    envelopes = tuple(
        EventEnvelope(
            event=event,
            decision=(
                None
                if event.decision_id is None
                else request.event_store.get_decision(event.decision_id)
            ),
            effect=effects.get(event.event_id),
            grant=_grant_for_event(request.event_store, event),
            revocation=revocations.get(event.event_id),
        )
        for event in events
    )
    artifacts = _capture_artifacts(request, events)
    heads = tuple(
        _memory_head(request, key, artifact_id)
        for key, artifact_id in request.memory_entries
    )
    return RunStoreSnapshot(envelopes, artifacts, heads)


def restore_run_store(snapshot: RunStoreSnapshot, setup: StoreRestoreSetup) -> None:
    """把冻结前缀逻辑导入一个空分支 Store。"""
    if setup.event_store.iter_run_events(setup.target_run_id):
        raise StoreIntegrityError("restore_checkpoint", "目标 Run 必须为空")
    for item in snapshot.artifacts:
        blob = setup.blob_store.put(item.content)
        setup.event_store.put_artifact(StoredArtifact(item.artifact, blob))
    for envelope in snapshot.envelopes:
        event = SecurityEvent.model_validate(
            {**envelope.event.model_dump(mode="json"), "run_id": setup.target_run_id}
        )
        setup.event_store.append_event(
            EventEnvelope(
                event=event,
                decision=envelope.decision,
                effect=envelope.effect,
                grant=envelope.grant,
                revocation=envelope.revocation,
            )
        )
    for head in snapshot.memory_heads:
        setup.event_store.set_memory_head(
            MemoryHead(
                run_id=setup.target_run_id,
                key=head.key,
                artifact_id=head.artifact_id,
                session_id=head.session_id,
                updated_event_id=head.updated_event_id,
            )
        )
    setup.blob_store.flush()
    setup.event_store.flush()


def _grant_for_event(store: EventStore, event: SecurityEvent) -> AuthorizationGrant | None:
    if event.event_type is not EventType.AUTH_GRANT:
        return None
    grant_id = event.metadata.get("grant_id")
    if not isinstance(grant_id, str):
        raise StoreIntegrityError("capture_checkpoint", "AUTH_GRANT 缺少 grant_id")
    grant = store.get_grant(grant_id)
    if grant is None:
        raise StoreIntegrityError("capture_checkpoint", f"Grant 不存在：{grant_id}")
    return grant


def _capture_artifacts(
    request: StoreCaptureRequest,
    events: tuple[SecurityEvent, ...],
) -> tuple[ArtifactSnapshot, ...]:
    artifact_ids = tuple(
        dict.fromkeys(artifact_id for event in events for artifact_id in event.output_artifact_ids)
    )
    snapshots: list[ArtifactSnapshot] = []
    for artifact_id in artifact_ids:
        artifact = request.event_store.get_artifact(artifact_id)
        reference = request.event_store.get_blob_ref(artifact_id)
        if artifact is None or reference is None:
            raise StoreIntegrityError("capture_checkpoint", f"Artifact 不完整：{artifact_id}")
        snapshots.append(ArtifactSnapshot(artifact, request.blob_store.get(reference)))
    return tuple(snapshots)


def _memory_head(request: StoreCaptureRequest, key: str, artifact_id: str) -> MemoryHead:
    head = request.event_store.get_memory_head(request.run_id, key)
    if head is None or head.artifact_id != artifact_id:
        raise StoreIntegrityError("capture_checkpoint", f"MemoryState 与 Store 不一致：{key}")
    return head
