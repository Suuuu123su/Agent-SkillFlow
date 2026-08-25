import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from skillflow.models.authorization import AuthorizationGrant
from skillflow.models.enums import CapabilityAction, EventType, Lifetime, Scope
from skillflow.models.events import SecurityEvent
from skillflow.models.resources import ResourceRef
from skillflow.store.errors import StoreIntegrityError
from skillflow.store.event_store import (
    EventEnvelope,
    RevocationRecord,
    RevocationTargetKind,
)
from skillflow.store.sqlite_store import SqliteEventStore

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def grant() -> AuthorizationGrant:
    return AuthorizationGrant(
        grant_id="grant-1",
        issuer_id="user-1",
        issuer_type="user",
        grantee_id="skill-a",
        action=CapabilityAction.FILE_READ,
        source_pattern=ResourceRef("workspace:/report.txt"),
        sink_pattern=ResourceRef("context:/task"),
        scope=Scope.EXACT_FILE,
        lifetime=Lifetime.TASK,
        task_id="task-1",
        valid_from=NOW,
        expires_at=NOW + timedelta(hours=1),
    )


def event(event_id: str, event_type: EventType, metadata: dict[str, str]) -> SecurityEvent:
    return SecurityEvent(
        event_id=event_id,
        run_id="run-1",
        task_id="task-1",
        session_id="session-1",
        timestamp=NOW,
        event_type=event_type,
        actor_id="user-1",
        metadata=metadata,
    )


def test_grant_and_auth_grant_event_commit_atomically(tmp_path: Path) -> None:
    # Given: 一个 USER 签发的结构化 Grant 及其 AUTH_GRANT Event
    candidate = grant()
    issued = event("event-grant", EventType.AUTH_GRANT, {"grant_id": candidate.grant_id})
    with SqliteEventStore(tmp_path / "state.sqlite") as store:
        # When: 在同一 Envelope 中追加
        store.append_event(EventEnvelope(issued, grant=candidate))

        # Then: Event 与 Grant 都可按强类型合同读回
        assert store.get_event(issued.event_id) == issued
        assert store.get_grant(candidate.grant_id) == candidate
        assert store.iter_run_grants("run-1") == (candidate,)


def test_invalid_grant_envelope_rolls_back_both_facts(tmp_path: Path) -> None:
    # Given: Grant 错误绑定到普通 SESSION_START Event
    candidate = grant()
    invalid = event("event-invalid", EventType.SESSION_START, {"grant_id": candidate.grant_id})
    with SqliteEventStore(tmp_path / "state.sqlite") as store:
        # When/Then: 完整性检查拒绝并且不留下半条事实
        with pytest.raises(StoreIntegrityError):
            store.append_event(EventEnvelope(invalid, grant=candidate))
        assert store.get_event(invalid.event_id) is None
        assert store.get_grant(candidate.grant_id) is None


def test_revocation_is_append_only_and_does_not_rewrite_grant(tmp_path: Path) -> None:
    # Given: 已签发 Grant 与后续 AUTH_REVOKE
    database = tmp_path / "state.sqlite"
    candidate = grant()
    issued = event("event-grant", EventType.AUTH_GRANT, {"grant_id": candidate.grant_id})
    revoked_event = event(
        "event-revoke",
        EventType.AUTH_REVOKE,
        {"grant_id": candidate.grant_id},
    )
    revocation = RevocationRecord(
        revocation_id="revoke-1",
        target_kind=RevocationTargetKind.GRANT,
        target_id=candidate.grant_id,
        event_id=revoked_event.event_id,
        timestamp=NOW,
    )
    with SqliteEventStore(database) as store:
        store.append_event(EventEnvelope(issued, grant=candidate))

        # When: 追加撤销事实
        store.append_event(EventEnvelope(revoked_event, revocation=revocation))

        # Then: 原 Grant 不变，撤销作为独立记录按 Run 可读
        assert store.get_grant(candidate.grant_id) == candidate
        assert store.iter_run_revocations("run-1") == (revocation,)

    # And: 数据库触发器拒绝绕过接口改写 Grant 或删除撤销
    with sqlite3.connect(database) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE grants SET grant_json = '{}' WHERE grant_id = 'grant-1'")
        connection.rollback()
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("DELETE FROM revocations WHERE revocation_id = 'revoke-1'")
