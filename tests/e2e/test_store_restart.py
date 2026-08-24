import hashlib
from datetime import UTC, datetime
from pathlib import Path

from skillflow.models import (
    Artifact,
    ArtifactType,
    EventType,
    SecurityEvent,
    SecurityLabel,
    TrustLevel,
)
from skillflow.store.blob_store import RunBlobStore
from skillflow.store.event_store import EventEnvelope, MemoryHead, StoredArtifact
from skillflow.store.sqlite_store import SqliteEventStore
from skillflow.store.trace import build_run_trace

NOW = datetime(2026, 1, 1, tzinfo=UTC)
SECRET = b"PERSISTENT_MEMORY_SECRET_MUST_NOT_ENTER_TRACE"


def test_persistent_memory_and_safe_trace_survive_process_restart(tmp_path: Path) -> None:
    # Given: Session 1 把运行态内容写入 BlobStore，并提交 Memory Event
    experiment_root = tmp_path / "runs" / "experiment-1"
    database = experiment_root / "state.sqlite"
    blob_store = RunBlobStore(experiment_root, "run-1")
    event_store = SqliteEventStore(database)
    blob_ref = blob_store.put(SECRET)
    memory_artifact = Artifact(
        artifact_id="memory-artifact-1",
        artifact_type=ArtifactType.MEMORY,
        content_hash=hashlib.sha256(SECRET).hexdigest(),
        content_length=len(SECRET),
        mime_type="text/plain",
        created_by_event_id="memory-write-1",
        observed_label=SecurityLabel(
            origins=frozenset({"skill-a"}),
            trust=TrustLevel.UNTRUSTED,
            task_id="task-1",
            created_session_id="session-1",
        ),
    )
    write_event = SecurityEvent(
        event_id="memory-write-1",
        run_id="run-1",
        task_id="task-1",
        session_id="session-1",
        timestamp=NOW,
        event_type=EventType.MEMORY_WRITE,
        actor_id="skill-a",
        output_artifact_ids=(memory_artifact.artifact_id,),
        metadata={"unsafe_preview": SECRET.decode()},
    )
    event_store.put_artifact(StoredArtifact(memory_artifact, blob_ref))
    event_store.append_event(EventEnvelope(write_event))
    event_store.set_memory_head(
        MemoryHead(
            run_id="run-1",
            key="shared-memory",
            artifact_id=memory_artifact.artifact_id,
            session_id="session-1",
            updated_event_id=write_event.event_id,
        )
    )
    event_store.flush()
    blob_store.flush()
    event_store.close()
    blob_store.close()

    # When: 模拟进程重启，在 Session 2 读取 Memory 并生成安全 Trace
    reopened_blobs = RunBlobStore(experiment_root, "run-1")
    reopened_events = SqliteEventStore(database)
    head = reopened_events.get_memory_head("run-1", "shared-memory")
    assert head is not None
    restored_ref = reopened_events.get_blob_ref(head.artifact_id)
    assert restored_ref is not None
    restored_content = reopened_blobs.get(restored_ref)
    read_artifact = Artifact(
        artifact_id="context-artifact-2",
        artifact_type=ArtifactType.CONTEXT,
        content_hash=memory_artifact.content_hash,
        content_length=memory_artifact.content_length,
        mime_type=memory_artifact.mime_type,
        created_by_event_id="memory-read-2",
        observed_label=SecurityLabel(
            origins=memory_artifact.observed_label.origins,
            trust=memory_artifact.observed_label.trust,
            task_id="task-1",
            created_session_id="session-2",
            parent_artifact_ids=frozenset({memory_artifact.artifact_id}),
        ),
    )
    read_event = SecurityEvent(
        event_id="memory-read-2",
        run_id="run-1",
        task_id="task-1",
        session_id="session-2",
        timestamp=NOW,
        event_type=EventType.MEMORY_READ,
        actor_id="skill-b",
        input_artifact_ids=(memory_artifact.artifact_id,),
        output_artifact_ids=(read_artifact.artifact_id,),
    )
    reopened_events.put_artifact(StoredArtifact(read_artifact, restored_ref))
    reopened_events.append_event(EventEnvelope(read_event))
    trace_before_close = build_run_trace(reopened_events, "run-1")
    reopened_events.close()
    reopened_blobs.close()

    # Then: 内容与历史可恢复，Trace 稳定且不含秘密明文
    final_events = SqliteEventStore(database)
    trace_after_reopen = build_run_trace(final_events, "run-1")
    history = final_events.iter_run_events("run-1")
    final_events.close()
    assert restored_content == SECRET
    assert tuple(event.event_id for event in history) == ("memory-write-1", "memory-read-2")
    assert trace_before_close.trace_hash == trace_after_reopen.trace_hash
    assert SECRET.decode() not in trace_after_reopen.model_dump_json()
