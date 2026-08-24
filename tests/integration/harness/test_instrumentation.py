from datetime import UTC, datetime
from pathlib import Path

import pytest

from skillflow.instrumentation.context_proxy import InstrumentedContext
from skillflow.instrumentation.errors import (
    MemoryKeyMissingError,
    WorkspaceEscapeError,
)
from skillflow.instrumentation.file_proxy import InstrumentedFile
from skillflow.instrumentation.memory_proxy import InstrumentedMemory, MemoryState
from skillflow.models.enums import ArtifactType, EventType
from skillflow.models.resources import ResourceRef
from skillflow.runtime.determinism import DeterministicIdFactory, VirtualClock
from skillflow.runtime.session import (
    ActorCall,
    RuntimeDependencies,
    RuntimeRecorder,
    SessionIdentity,
)
from skillflow.store.blob_store import RunBlobStore
from skillflow.store.sqlite_store import SqliteEventStore

START = datetime(2026, 1, 1, tzinfo=UTC)


def skill_call() -> ActorCall:
    return ActorCall(actor_id="skill-a", call_id="call-1")


def make_dependencies(
    store: SqliteEventStore,
    blobs: RunBlobStore,
    ids: DeterministicIdFactory,
) -> RuntimeDependencies:
    return RuntimeDependencies(
        event_store=store,
        blob_store=blobs,
        clock=VirtualClock(START),
        id_factory=ids,
    )


def make_recorder(dependencies: RuntimeDependencies, session_id: str) -> RuntimeRecorder:
    return RuntimeRecorder(
        SessionIdentity(run_id="run-1", task_id="task-1", session_id=session_id),
        dependencies,
    )


def test_context_add_creates_new_artifact_and_event(tmp_path: Path) -> None:
    # Given: 一个空 Session Context
    with (
        SqliteEventStore(tmp_path / "state.sqlite") as store,
        RunBlobStore(tmp_path, "run-1") as blobs,
    ):
        recorder = make_recorder(
            make_dependencies(store, blobs, DeterministicIdFactory("seed-context")),
            "session-1",
        )
        context = InstrumentedContext(recorder)

        # When: Skill 把内容加入 Context
        artifact = context.add(b"alpha", skill_call())

        # Then: 内容进入新 Artifact，且历史包含 CONTEXT_ADD
        assert artifact.artifact_type is ArtifactType.CONTEXT
        assert recorder.read_content(artifact.artifact_id) == b"alpha"
        assert store.iter_run_events("run-1")[-1].event_type is EventType.CONTEXT_ADD


def test_context_read_and_summarize_preserve_parent_edges(tmp_path: Path) -> None:
    # Given: Context 中已有两个独立 Artifact
    with (
        SqliteEventStore(tmp_path / "state.sqlite") as store,
        RunBlobStore(tmp_path, "run-1") as blobs,
    ):
        recorder = make_recorder(
            make_dependencies(store, blobs, DeterministicIdFactory("seed-transform")),
            "session-1",
        )
        context = InstrumentedContext(recorder)
        first = context.add(b"alpha", skill_call())
        second = context.read(first.artifact_id, skill_call())

        # When: 对两个版本做确定性摘要
        summary = context.summarize((first.artifact_id, second.artifact_id), skill_call())

        # Then: 摘要是新版本，并显式连接两个父 Artifact
        assert summary.artifact_id not in {first.artifact_id, second.artifact_id}
        assert summary.observed_label.parent_artifact_ids == frozenset(
            {first.artifact_id, second.artifact_id}
        )
        assert recorder.read_content(summary.artifact_id) == b"alpha\nalpha"
        assert store.iter_run_events("run-1")[-1].event_type is EventType.CONTEXT_SUMMARIZE


def test_memory_read_in_new_session_links_written_artifact(tmp_path: Path) -> None:
    # Given: Session 1 写入一个 Persistent Memory 版本
    with (
        SqliteEventStore(tmp_path / "state.sqlite") as store,
        RunBlobStore(tmp_path, "run-1") as blobs,
    ):
        dependencies = make_dependencies(store, blobs, DeterministicIdFactory("seed-memory"))
        state = MemoryState()
        session_one = make_recorder(dependencies, "session-1")
        source = InstrumentedContext(session_one).add(b"remember-me", skill_call())
        written = InstrumentedMemory(session_one, state).write(
            "shared",
            source.artifact_id,
            skill_call(),
        )
        session_two = make_recorder(dependencies, "session-2")

        # When: Session 2 读取相同 Memory key
        restored = InstrumentedMemory(session_two, state).read("shared", skill_call())

        # Then: 新 Artifact 明确连接 Session 1 写入版本
        assert restored.observed_label.parent_artifact_ids == frozenset({written.artifact_id})
        assert restored.observed_label.created_session_id == "session-2"
        assert session_two.read_content(restored.artifact_id) == b"remember-me"
        assert store.iter_run_events("run-1")[-1].input_artifact_ids == (written.artifact_id,)


def test_memory_delete_makes_key_unreadable_without_changing_history(tmp_path: Path) -> None:
    # Given: 一个已写入的 Memory key
    with (
        SqliteEventStore(tmp_path / "state.sqlite") as store,
        RunBlobStore(tmp_path, "run-1") as blobs,
    ):
        recorder = make_recorder(
            make_dependencies(store, blobs, DeterministicIdFactory("seed-delete")),
            "session-1",
        )
        state = MemoryState()
        source = InstrumentedContext(recorder).add(b"temporary", skill_call())
        memory = InstrumentedMemory(recorder, state)
        memory.write("temporary", source.artifact_id, skill_call())

        # When: 删除当前 Memory key
        memory.delete("temporary", skill_call())

        # Then: 后续读取失败，但 MEMORY_DELETE 作为历史保留
        with pytest.raises(MemoryKeyMissingError):
            memory.read("temporary", skill_call())
        assert store.iter_run_events("run-1")[-1].event_type is EventType.MEMORY_DELETE
        assert store.get_memory_head("run-1", "temporary") is None


def test_file_read_is_confined_to_workspace_root(tmp_path: Path) -> None:
    # Given: Workspace 内一个文件和一个绕过模型构造的逃逸引用
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "report.txt").write_bytes(b"safe-report")
    escaped = ResourceRef.model_construct(root="workspace:/../outside.txt")
    with (
        SqliteEventStore(tmp_path / "state.sqlite") as store,
        RunBlobStore(tmp_path, "run-1") as blobs,
    ):
        recorder = make_recorder(
            make_dependencies(store, blobs, DeterministicIdFactory("seed-file")),
            "session-1",
        )
        files = InstrumentedFile(workspace, recorder)

        # When: 读取合法文件
        artifact = files.read(ResourceRef("workspace:/report.txt"), skill_call())

        # Then: 内容被插桩，逃逸引用仍由文件边界拒绝
        assert recorder.read_content(artifact.artifact_id) == b"safe-report"
        assert artifact.artifact_type is ArtifactType.FILE
        with pytest.raises(WorkspaceEscapeError):
            files.read(escaped, skill_call())
