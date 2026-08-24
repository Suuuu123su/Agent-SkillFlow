from datetime import UTC, datetime
from pathlib import Path

import pytest

from skillflow.adapters.base import SkillBinding
from skillflow.instrumentation.context_proxy import InstrumentedContext
from skillflow.instrumentation.errors import SkillLifecycleError
from skillflow.instrumentation.skill_proxy import InstrumentedSkill, SkillState
from skillflow.models.enums import EventType
from skillflow.models.references import FixtureImplementationRef
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


def make_recorder(store: SqliteEventStore, blobs: RunBlobStore) -> RuntimeRecorder:
    return RuntimeRecorder(
        SessionIdentity(run_id="run-1", task_id="task-1", session_id="session-1"),
        RuntimeDependencies(
            event_store=store,
            blob_store=blobs,
            clock=VirtualClock(START),
            id_factory=DeterministicIdFactory("seed-skill"),
        ),
    )


def test_skill_lifecycle_records_all_six_boundaries(tmp_path: Path) -> None:
    # Given: 一个尚未安装的固定 fixture Skill
    binding = SkillBinding(
        skill_id="reader",
        implementation=FixtureImplementationRef("fixture://reader"),
    )
    with (
        SqliteEventStore(tmp_path / "state.sqlite") as store,
        RunBlobStore(tmp_path, "run-1") as blobs,
    ):
        recorder = make_recorder(store, blobs)
        skills = InstrumentedSkill(recorder, SkillState())
        harness = ActorCall("harness", None)
        skill = ActorCall("reader", "call-1")
        source = InstrumentedContext(recorder).add(b"input", skill)

        # When: Skill 完成 install/load/invoke/return/revoke/unload 生命周期
        skills.install(binding, harness)
        skills.load("reader", harness)
        invocation = skills.invoke("reader", (source.artifact_id,), skill)
        output = skills.return_output(invocation, b"output", (source.artifact_id,))
        skills.revoke("reader", ActorCall("user", None))
        skills.unload("reader", harness)

        # Then: 六个边界均作为追加事实存在，return 输出连接输入
        lifecycle_events = tuple(
            event
            for event in store.iter_run_events("run-1")
            if event.event_type.name.startswith("SKILL_")
        )
        assert tuple(event.event_type for event in lifecycle_events) == (
            EventType.SKILL_INSTALL,
            EventType.SKILL_LOAD,
            EventType.SKILL_INVOKE,
            EventType.SKILL_RETURN,
            EventType.SKILL_REVOKE,
            EventType.SKILL_UNLOAD,
        )
        assert tuple(event.metadata["skill_id"] for event in lifecycle_events) == (
            "reader",
            "reader",
            "reader",
            "reader",
            "reader",
            "reader",
        )
        assert output.observed_label.parent_artifact_ids == frozenset({source.artifact_id})
        assert recorder.read_content(output.artifact_id) == b"output"


def test_revoked_skill_cannot_be_loaded_or_invoked(tmp_path: Path) -> None:
    # Given: 一个已撤销 Skill
    binding = SkillBinding(
        skill_id="reader",
        implementation=FixtureImplementationRef("fixture://reader"),
    )
    with (
        SqliteEventStore(tmp_path / "state.sqlite") as store,
        RunBlobStore(tmp_path, "run-1") as blobs,
    ):
        skills = InstrumentedSkill(make_recorder(store, blobs), SkillState())
        harness = ActorCall("harness", None)
        skills.install(binding, harness)
        skills.load("reader", harness)
        skills.revoke("reader", ActorCall("user", None))

        # When/Then: 撤销后不能再次 load，也不能 invoke
        with pytest.raises(SkillLifecycleError):
            skills.load("reader", harness)
        with pytest.raises(SkillLifecycleError):
            skills.invoke("reader", (), ActorCall("reader", "call-2"))
