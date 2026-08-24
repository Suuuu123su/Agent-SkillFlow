"""不包含内容明文的稳定 Trace 投影。"""

import hashlib
import json
from datetime import datetime

from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.effects import CapabilityEffect
from skillflow.models.enums import ArtifactType, EventType
from skillflow.store.errors import StoreIntegrityError
from skillflow.store.event_store import EventStore


class ArtifactTraceMetadata(StrictModel):
    """Trace 中允许导出的 Artifact 元数据。"""

    artifact_id: NonEmptyStr
    artifact_type: ArtifactType
    content_hash: NonEmptyStr
    content_length: int
    mime_type: NonEmptyStr


class EventTraceRecord(StrictModel):
    """去除任意内容字段后的 Event 投影。"""

    event_id: NonEmptyStr
    run_id: NonEmptyStr
    task_id: NonEmptyStr
    session_id: NonEmptyStr
    call_id: NonEmptyStr | None
    timestamp: datetime
    event_type: EventType
    actor_id: NonEmptyStr
    inputs: tuple[ArtifactTraceMetadata, ...]
    outputs: tuple[ArtifactTraceMetadata, ...]
    requested_effect: CapabilityEffect | None
    decision_id: NonEmptyStr | None


class RunTrace(StrictModel):
    """一个 Run 的安全投影及其稳定哈希。"""

    run_id: NonEmptyStr
    events: tuple[EventTraceRecord, ...]
    trace_hash: NonEmptyStr


class _TracePayload(StrictModel):
    """参与哈希但不包含自引用 trace_hash 的载荷。"""

    run_id: NonEmptyStr
    events: tuple[EventTraceRecord, ...]


def build_run_trace(store: EventStore, run_id: str) -> RunTrace:
    """从 EventStore 构建默认脱敏 Trace。"""
    records = tuple(
        EventTraceRecord(
            event_id=event.event_id,
            run_id=event.run_id,
            task_id=event.task_id,
            session_id=event.session_id,
            call_id=event.call_id,
            timestamp=event.timestamp,
            event_type=event.event_type,
            actor_id=event.actor_id,
            inputs=_artifact_metadata(store, event.input_artifact_ids),
            outputs=_artifact_metadata(store, event.output_artifact_ids),
            requested_effect=event.requested_effect,
            decision_id=event.decision_id,
        )
        for event in store.iter_run_events(run_id)
    )
    payload = _TracePayload(run_id=run_id, events=records)
    canonical = json.dumps(
        payload.model_dump(mode="json"),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return RunTrace(
        run_id=run_id,
        events=records,
        trace_hash=hashlib.sha256(canonical).hexdigest(),
    )


def _artifact_metadata(
    store: EventStore,
    artifact_ids: tuple[str, ...],
) -> tuple[ArtifactTraceMetadata, ...]:
    records: list[ArtifactTraceMetadata] = []
    for artifact_id in artifact_ids:
        artifact = store.get_artifact(artifact_id)
        if artifact is None:
            raise StoreIntegrityError("build_run_trace", f"Artifact 不存在：{artifact_id}")
        records.append(
            ArtifactTraceMetadata(
                artifact_id=artifact.artifact_id,
                artifact_type=artifact.artifact_type,
                content_hash=artifact.content_hash,
                content_length=artifact.content_length,
                mime_type=artifact.mime_type,
            )
        )
    return tuple(records)
