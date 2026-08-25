from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from skillflow.adapters.base import HarnessSession
from skillflow.adapters.mock_harness import (
    BenchmarkController,
    MockHarnessAdapter,
    MockHarnessConfig,
)
from skillflow.benchmark.scripted_backend import ScriptedBackend
from skillflow.instrumentation.decision_stub import StubDecisionProvider
from skillflow.instrumentation.errors import HarnessStateError
from skillflow.models.authorization import AuthorizationGrant
from skillflow.models.enums import (
    CapabilityAction,
    Decision,
    EventType,
    Lifetime,
    PrincipalType,
    Scope,
)
from skillflow.models.resources import ResourceRef
from skillflow.runtime.determinism import DeterministicIdFactory, VirtualClock
from skillflow.runtime.session import RuntimeDependencies
from skillflow.store.blob_store import RunBlobStore
from skillflow.store.event_store import RevocationTargetKind
from skillflow.store.sqlite_store import SqliteEventStore

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def grant() -> AuthorizationGrant:
    return AuthorizationGrant(
        grant_id="grant-confirmed",
        issuer_id="user-1",
        issuer_type=PrincipalType.USER,
        grantee_id="skill-a",
        action=CapabilityAction.FILE_READ,
        source_pattern=ResourceRef("workspace:/report.txt"),
        sink_pattern=ResourceRef("context:/task"),
        scope=Scope.EXACT_FILE,
        lifetime=Lifetime.CALL,
        task_id="task-1",
        session_id="session-1",
        call_id="call-1",
        valid_from=NOW,
        expires_at=NOW + timedelta(hours=1),
    )


def test_only_benchmark_user_can_issue_and_revoke_structured_grant(
    tmp_path: Path,
) -> None:
    # Given: Skill 无法接触的 BenchmarkController 与一个活动 Session
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    with (
        SqliteEventStore(tmp_path / "state.sqlite") as store,
        RunBlobStore(tmp_path, "run-1") as blobs,
    ):
        harness = MockHarnessAdapter(
            MockHarnessConfig(
                run_id="run-1",
                task_id="task-1",
                workspace_root=workspace,
                dependencies=RuntimeDependencies(
                    event_store=store,
                    blob_store=blobs,
                    clock=VirtualClock(NOW),
                    id_factory=DeterministicIdFactory("t08-confirm"),
                ),
            ),
            ScriptedBackend({}),
            StubDecisionProvider({"unused": Decision.DENY}),
        )
        harness.start_session(HarnessSession("session-1"))
        controller = BenchmarkController(harness)
        candidate = grant()

        # When/Then: Skill 身份不能伪造确认，USER 才能追加结构化 Grant
        with pytest.raises(HarnessStateError):
            controller.confirm_tool(candidate, PrincipalType.SKILL)
        controller.confirm_tool(candidate, PrincipalType.USER)
        assert store.get_grant(candidate.grant_id) == candidate

        # And: USER 撤销只追加 AUTH_REVOKE，不修改原 Grant
        controller.revoke_grant(candidate.grant_id, PrincipalType.USER)
        revocations = store.iter_run_revocations("run-1")
        assert store.get_grant(candidate.grant_id) == candidate
        assert len(revocations) == 1
        assert revocations[0].target_kind is RevocationTargetKind.GRANT
        assert tuple(event.event_type for event in store.iter_run_events("run-1")) == (
            EventType.SESSION_START,
            EventType.AUTH_GRANT,
            EventType.AUTH_REVOKE,
        )

        harness.end_session()
