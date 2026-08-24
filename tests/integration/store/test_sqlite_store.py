import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from skillflow.models import (
    Artifact,
    ArtifactType,
    CapabilityEffect,
    Decision,
    DecisionRecord,
    EffectRecord,
    EventType,
    SecurityEvent,
    SecurityLabel,
    TrustLevel,
)
from skillflow.store.blob_store import BlobRef
from skillflow.store.errors import (
    StoreClosedError,
    StoreConflictError,
    StoreIntegrityError,
)
from skillflow.store.event_store import EventEnvelope, StoredArtifact
from skillflow.store.sqlite_store import SqliteEventStore

NOW = datetime(2026, 1, 1, tzinfo=UTC)
REQUIRED_TABLES = {
    "runs",
    "sessions",
    "principals",
    "artifacts",
    "events",
    "event_inputs",
    "event_outputs",
    "grants",
    "decisions",
    "effects",
    "revocations",
    "memory_heads",
}


def make_artifact(artifact_id: str, creator_event_id: str) -> Artifact:
    return Artifact(
        artifact_id=artifact_id,
        artifact_type=ArtifactType.MEMORY,
        content_hash="a" * 64,
        content_length=7,
        mime_type="text/plain",
        created_by_event_id=creator_event_id,
        observed_label=SecurityLabel(
            origins=frozenset({"skill-a"}),
            trust=TrustLevel.USER,
            task_id="task-1",
            created_session_id="session-1",
        ),
    )


def make_event(
    event_id: str,
    inputs: tuple[str, ...] = (),
    outputs: tuple[str, ...] = (),
) -> SecurityEvent:
    return SecurityEvent(
        event_id=event_id,
        run_id="run-1",
        task_id="task-1",
        session_id="session-1",
        timestamp=NOW,
        event_type=EventType.ARTIFACT_REGISTER,
        actor_id="skill-a",
        input_artifact_ids=inputs,
        output_artifact_ids=outputs,
    )


def test_schema_creates_all_t04_tables(tmp_path: Path) -> None:
    # Given: 一个新建的 SQLite EventStore
    database = tmp_path / "state.sqlite"
    store = SqliteEventStore(database)
    store.close()

    # When: 从 SQLite 元数据读取表名
    with sqlite3.connect(database) as connection:
        rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()

    # Then: T04 列出的持久状态表全部存在
    assert {str(row[0]) for row in rows} >= REQUIRED_TABLES


def test_event_and_artifact_round_trip_in_append_order(tmp_path: Path) -> None:
    # Given: 两个 Artifact 及其按顺序产生的 Event
    store = SqliteEventStore(tmp_path / "state.sqlite")
    first_artifact = make_artifact("artifact-1", "event-1")
    second_artifact = make_artifact("artifact-2", "event-2")
    first_event = make_event("event-1", outputs=(first_artifact.artifact_id,))
    second_event = make_event(
        "event-2",
        inputs=(first_artifact.artifact_id,),
        outputs=(second_artifact.artifact_id,),
    )
    store.put_artifact(StoredArtifact(first_artifact))
    store.put_artifact(StoredArtifact(second_artifact))

    # When: 依次追加并读取
    store.append_event(EventEnvelope(first_event))
    store.append_event(EventEnvelope(second_event))
    restored = store.get_artifact(second_artifact.artifact_id)
    history = store.iter_run_events("run-1")
    store.close()

    # Then: 模型无损且顺序等于追加顺序
    assert restored == second_artifact
    assert history == (first_event, second_event)


def test_duplicate_event_id_is_rejected(tmp_path: Path) -> None:
    # Given: 已经追加的 Event
    store = SqliteEventStore(tmp_path / "state.sqlite")
    event = make_event("event-1")
    store.append_event(EventEnvelope(event))

    # When/Then: 重复 event_id 作为显式冲突失败
    with pytest.raises(StoreConflictError):
        store.append_event(EventEnvelope(event))
    store.close()


def test_missing_artifact_rolls_back_event_decision_and_effect(tmp_path: Path) -> None:
    # Given: 一个引用不存在输入 Artifact 的原子 Event Envelope
    store = SqliteEventStore(tmp_path / "state.sqlite")
    event = make_event("event-fail", inputs=("artifact-missing",)).model_copy(
        update={"decision_id": "decision-fail"}
    )
    decision = DecisionRecord(
        decision_id="decision-fail",
        request_event_id=event.event_id,
        enforcement_mode="enforce",
        baseline_result=Decision.DENY,
        policy_result=Decision.DENY,
        authorized=False,
        executed=False,
    )
    effect = EffectRecord(
        effect_id="effect-fail",
        effect=CapabilityEffect.model_validate(
            {
                "source": "workspace:/secret.txt",
                "action": "network.send",
                "sink": "mock://external",
                "scope": "exact-file",
                "lifetime": "call",
                "sensitivity": 4,
            }
        ),
        request_event_id=event.event_id,
        decision_id=decision.decision_id,
        executed=False,
    )

    # When: 原子追加因外键失败
    with pytest.raises(StoreIntegrityError):
        store.append_event(EventEnvelope(event, decision, effect))

    # Then: Event、Decision 和 Effect 均未留下半条记录
    assert store.get_event(event.event_id) is None
    assert store.get_decision(decision.decision_id) is None
    assert store.get_effect(effect.effect_id) is None
    store.close()


def test_event_decision_and_effect_commit_as_one_envelope(tmp_path: Path) -> None:
    # Given: 相互引用的 Event、Decision 与 Effect
    store = SqliteEventStore(tmp_path / "state.sqlite")
    capability = CapabilityEffect.model_validate(
        {
            "source": "workspace:/report.txt",
            "action": "network.send",
            "sink": "mock://external",
            "scope": "exact-file",
            "lifetime": "call",
            "sensitivity": 2,
        }
    )
    event = make_event("event-request").model_copy(
        update={"decision_id": "decision-1", "requested_effect": capability}
    )
    decision = DecisionRecord(
        decision_id="decision-1",
        request_event_id=event.event_id,
        enforcement_mode="monitor",
        baseline_result=Decision.ALLOW,
        policy_result=Decision.DENY,
        authorized=False,
        executed=False,
    )
    effect = EffectRecord(
        effect_id="effect-1",
        effect=capability,
        request_event_id=event.event_id,
        decision_id=decision.decision_id,
        executed=False,
    )

    # When: 作为一个 Envelope 追加
    store.append_event(EventEnvelope(event, decision, effect))

    # Then: 三个事实同时可读且模型无损
    assert store.get_event(event.event_id) == event
    assert store.get_decision(decision.decision_id) == decision
    assert store.get_effect(effect.effect_id) == effect
    store.close()


def test_effect_must_match_event_decision_and_requested_capability(tmp_path: Path) -> None:
    # Given: 数据库已有另一个合法决策；新 Effect 错用它且能力内容不一致
    store = SqliteEventStore(tmp_path / "state.sqlite")
    other_event = make_event("event-other").model_copy(update={"decision_id": "decision-other"})
    other_decision = DecisionRecord(
        decision_id="decision-other",
        request_event_id=other_event.event_id,
        enforcement_mode="monitor",
        baseline_result=Decision.DENY,
        policy_result=Decision.DENY,
        authorized=False,
        executed=False,
    )
    store.append_event(EventEnvelope(other_event, other_decision))
    requested = CapabilityEffect.model_validate(
        {
            "source": "workspace:/report.txt",
            "action": "network.send",
            "sink": "mock://external",
            "scope": "exact-file",
            "lifetime": "call",
            "sensitivity": 2,
        }
    )
    event = make_event("event-request").model_copy(
        update={"decision_id": "decision-1", "requested_effect": requested}
    )
    decision = DecisionRecord(
        decision_id="decision-1",
        request_event_id=event.event_id,
        enforcement_mode="monitor",
        baseline_result=Decision.ALLOW,
        policy_result=Decision.DENY,
        authorized=False,
        executed=False,
    )
    mismatched_effect = EffectRecord(
        effect_id="effect-1",
        effect=requested.model_copy(update={"sensitivity": 4}),
        request_event_id=event.event_id,
        decision_id="decision-other",
        executed=False,
    )

    # When/Then: Envelope 在接触数据库前作为显式完整性错误失败
    with pytest.raises(StoreIntegrityError):
        store.append_event(EventEnvelope(event, decision, mismatched_effect))
    assert store.get_event(event.event_id) is None
    assert store.get_decision(decision.decision_id) is None
    assert store.get_effect(mismatched_effect.effect_id) is None
    store.close()


def test_result_effect_and_decision_must_share_request_event(tmp_path: Path) -> None:
    # Given: 两个合法请求和一个把 Decision/Effect 分别指向不同请求的结果 Envelope
    store = SqliteEventStore(tmp_path / "state.sqlite")
    capability = CapabilityEffect.model_validate(
        {
            "source": "workspace:/report.txt",
            "action": "network.send",
            "sink": "mock://external",
            "scope": "exact-file",
            "lifetime": "call",
            "sensitivity": 2,
        }
    )
    first_request = make_event("request-one").model_copy(update={"requested_effect": capability})
    second_request = make_event("request-two").model_copy(update={"requested_effect": capability})
    store.append_event(EventEnvelope(first_request))
    store.append_event(EventEnvelope(second_request))
    result = make_event("result").model_copy(
        update={"decision_id": "decision-1", "requested_effect": capability}
    )
    decision = DecisionRecord(
        decision_id="decision-1",
        request_event_id=first_request.event_id,
        enforcement_mode="monitor",
        baseline_result=Decision.ALLOW,
        policy_result=Decision.ALLOW,
        authorized=False,
        executed=True,
    )
    effect = EffectRecord(
        effect_id="effect-1",
        effect=capability,
        request_event_id=second_request.event_id,
        decision_id=decision.decision_id,
        result_event_id=result.event_id,
        tool_receipt_id="receipt-1",
        executed=True,
    )

    # When/Then: 不能把两个独立请求拼成貌似完整的 Tool 结果
    with pytest.raises(StoreIntegrityError):
        store.append_event(EventEnvelope(result, decision, effect))
    assert store.get_event(result.event_id) is None
    assert store.get_decision(decision.decision_id) is None
    assert store.get_effect(effect.effect_id) is None
    store.close()


def test_output_artifact_has_only_one_generating_event(tmp_path: Path) -> None:
    # Given: 已由 event-1 生成的输出 Artifact
    store = SqliteEventStore(tmp_path / "state.sqlite")
    artifact = make_artifact("artifact-1", "event-1")
    store.put_artifact(StoredArtifact(artifact))
    store.append_event(EventEnvelope(make_event("event-1", outputs=(artifact.artifact_id,))))

    # When/Then: 第二个 Event 不能再次声明同一输出
    with pytest.raises(StoreIntegrityError):
        store.append_event(EventEnvelope(make_event("event-2", outputs=(artifact.artifact_id,))))
    assert store.get_event("event-2") is None
    store.close()


def test_event_rejects_output_blob_from_another_run(tmp_path: Path) -> None:
    # Given: run-1 Event 的输出 Artifact 错误绑定到 run-2 Blob
    store = SqliteEventStore(tmp_path / "state.sqlite")
    artifact = make_artifact("artifact-cross-run", "event-cross-run")
    foreign_blob = BlobRef(
        run_id="run-2",
        blob_id="b" * 48,
        content_hash=artifact.content_hash,
        content_length=artifact.content_length,
    )
    store.put_artifact(StoredArtifact(artifact, foreign_blob))
    event = make_event("event-cross-run", outputs=(artifact.artifact_id,))

    # When/Then: 原子追加拒绝跨 Run Blob，且不留下 Event
    with pytest.raises(StoreIntegrityError):
        store.append_event(EventEnvelope(event))
    assert store.get_event(event.event_id) is None
    store.close()


def test_database_triggers_reject_event_update_and_edge_delete(tmp_path: Path) -> None:
    # Given: 一个已提交 Event 和输出边的数据库
    database = tmp_path / "state.sqlite"
    store = SqliteEventStore(database)
    artifact = make_artifact("artifact-1", "event-1")
    store.put_artifact(StoredArtifact(artifact))
    store.append_event(EventEnvelope(make_event("event-1", outputs=(artifact.artifact_id,))))

    # When/Then: 绕过公共接口的 UPDATE 与 DELETE 仍被数据库拒绝
    with sqlite3.connect(database) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE events SET actor_id = 'tampered' WHERE event_id = 'event-1'")
        connection.rollback()
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("DELETE FROM event_outputs WHERE event_id = 'event-1'")
    store.close()


def test_closed_event_store_rejects_access(tmp_path: Path) -> None:
    # Given: 已关闭的 EventStore
    store = SqliteEventStore(tmp_path / "state.sqlite")
    store.close()

    # When/Then: 读取不会静默创建新连接
    with pytest.raises(StoreClosedError):
        store.get_event("event-1")
