from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from skillflow.instrumentation.file_proxy import InstrumentedFile
from skillflow.instrumentation.memory_proxy import InstrumentedMemory, MemoryState
from skillflow.instrumentation.mock_tools import (
    MockNetworkSink,
    MockShellSink,
    MockToolAdapter,
    MockToolServices,
)
from skillflow.instrumentation.tool_proxy import DeniedToolCall, ExecutedToolCall, InstrumentedTool
from skillflow.instrumentation.tool_types import ReadFileArgs, ToolCallRequest
from skillflow.models.authorization import AuthorizationGrant
from skillflow.models.effects import CapabilityEffect
from skillflow.models.enums import (
    CapabilityAction,
    Decision,
    EnforcementMode,
    Lifetime,
    Scope,
)
from skillflow.models.manifest import SkillManifest
from skillflow.models.resources import ResourceRef
from skillflow.policy import PolicyReasonCode
from skillflow.policy.runtime import RuntimePolicySetup, StoredPolicyDecisionProvider
from skillflow.runtime.determinism import DeterministicIdFactory, VirtualClock
from skillflow.runtime.session import (
    ActorCall,
    RuntimeDependencies,
    RuntimeRecorder,
    SessionIdentity,
)
from skillflow.store.blob_store import RunBlobStore
from skillflow.store.sqlite_store import SqliteEventStore

NOW = datetime(2026, 1, 1, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class PolicyStack:
    recorder: RuntimeRecorder
    tool: InstrumentedTool


@dataclass(frozen=True, slots=True)
class PolicyStackConfig:
    mode: EnforcementMode
    auto_approve: bool
    confirmation_allowed: bool


def manifest() -> SkillManifest:
    return SkillManifest(
        schema_version="0.1",
        id="skill-a",
        requested_permissions=(
            CapabilityEffect(
                source=ResourceRef("workspace:/report.txt"),
                action=CapabilityAction.FILE_READ,
                sink=ResourceRef("context:/task"),
                scope=Scope.EXACT_FILE,
                lifetime=Lifetime.CALL,
                sensitivity=1,
            ),
        ),
    )


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


def make_stack(
    tmp_path: Path,
    store: SqliteEventStore,
    blobs: RunBlobStore,
    config: PolicyStackConfig,
) -> PolicyStack:
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    (workspace / "report.txt").write_text("report", encoding="utf-8")
    recorder = RuntimeRecorder(
        SessionIdentity("run-1", "task-1", "session-1"),
        RuntimeDependencies(
            event_store=store,
            blob_store=blobs,
            clock=VirtualClock(NOW),
            id_factory=DeterministicIdFactory("t08-policy"),
        ),
    )
    provider = StoredPolicyDecisionProvider(
        store,
        RuntimePolicySetup(
            run_id="run-1",
            manifests={"skill-a": manifest()},
            structural_decisions={"read": Decision.ALLOW},
            enforcement_mode=config.mode,
            auto_approve_tools=config.auto_approve,
            implicit_text_authorization=False,
            confirmation_allowed=config.confirmation_allowed,
        ),
    )
    tool = InstrumentedTool(
        recorder,
        provider,
        MockToolAdapter(
            MockToolServices(
                files=InstrumentedFile(workspace, recorder),
                memory=InstrumentedMemory(recorder, MemoryState()),
                network=MockNetworkSink(),
                shell=MockShellSink(),
            )
        ),
    )
    return PolicyStack(recorder, tool)


def request() -> ToolCallRequest:
    return ToolCallRequest(
        actor_id="skill-a",
        call_id="call-1",
        action_id="read-report",
        decision_key="read",
        arguments=ReadFileArgs(
            resource=ResourceRef("workspace:/report.txt"),
            sensitivity=1,
        ),
    )


def test_monitor_executes_baseline_allow_without_authorization_laundering(
    tmp_path: Path,
) -> None:
    # Given: 无 Grant、自动批准、禁止新确认的 monitor Harness
    with (
        SqliteEventStore(tmp_path / "state.sqlite") as store,
        RunBlobStore(tmp_path, "run-1") as blobs,
    ):
        stack = make_stack(
            tmp_path,
            store,
            blobs,
            PolicyStackConfig(
                mode=EnforcementMode.MONITOR,
                auto_approve=True,
                confirmation_allowed=False,
            ),
        )

        # When: baseline 会执行，但 Policy 明确拒绝
        outcome = stack.tool.call(request())

        # Then: Mock Effect 发生，authorized 仍为 false
        assert isinstance(outcome, ExecutedToolCall)
        decision = store.get_decision(outcome.receipt.decision_id)
        assert decision is not None
        assert decision.baseline_result is Decision.ALLOW
        assert decision.policy_result is Decision.DENY
        assert not decision.authorized
        assert decision.executed
        assert decision.manifest_id == "skill-a"
        assert decision.reason_codes == (PolicyReasonCode.USER_GRANT_MISSING.value,)


def test_enforce_blocks_the_same_unauthorized_request(tmp_path: Path) -> None:
    # Given: 与 monitor 相同事实但 mode=enforce
    with (
        SqliteEventStore(tmp_path / "state.sqlite") as store,
        RunBlobStore(tmp_path, "run-1") as blobs,
    ):
        stack = make_stack(
            tmp_path,
            store,
            blobs,
            PolicyStackConfig(
                mode=EnforcementMode.ENFORCE,
                auto_approve=True,
                confirmation_allowed=False,
            ),
        )

        # When: 请求同一 Effect
        outcome = stack.tool.call(request())

        # Then: Decision 真值相同，但没有执行或 Receipt
        assert isinstance(outcome, DeniedToolCall)
        assert outcome.decision.baseline_result is Decision.ALLOW
        assert outcome.decision.policy_result is Decision.DENY
        assert not outcome.decision.executed
        assert store.iter_run_effects("run-1") == ()


def test_enforce_executes_only_after_manifest_and_grant_both_match(tmp_path: Path) -> None:
    # Given: 已经由 USER 特权入口记录的 task Grant
    with (
        SqliteEventStore(tmp_path / "state.sqlite") as store,
        RunBlobStore(tmp_path, "run-1") as blobs,
    ):
        stack = make_stack(
            tmp_path,
            store,
            blobs,
            PolicyStackConfig(
                mode=EnforcementMode.ENFORCE,
                auto_approve=False,
                confirmation_allowed=True,
            ),
        )
        stack.recorder.record_authorization_grant(grant(), ActorCall("user-1", None))

        # When: Skill 请求 Manifest 与 Grant 都覆盖的 Effect
        outcome = stack.tool.call(request())

        # Then: baseline/policy 均 ALLOW，Decision 可追溯三类证据
        assert isinstance(outcome, ExecutedToolCall)
        decision = store.get_decision(outcome.receipt.decision_id)
        assert decision is not None
        assert decision.baseline_result is Decision.ALLOW
        assert decision.policy_result is Decision.ALLOW
        assert decision.authorized
        assert decision.executed
        assert decision.manifest_id == "skill-a"
        assert decision.matched_grant_ids == ("grant-1",)
        assert outcome.pending.argument_artifact_id in decision.decision_basis_artifact_ids


def test_auth_revoke_blocks_only_subsequent_effects(tmp_path: Path) -> None:
    # Given: 第一次调用时 Grant 有效
    with (
        SqliteEventStore(tmp_path / "state.sqlite") as store,
        RunBlobStore(tmp_path, "run-1") as blobs,
    ):
        stack = make_stack(
            tmp_path,
            store,
            blobs,
            PolicyStackConfig(
                mode=EnforcementMode.ENFORCE,
                auto_approve=False,
                confirmation_allowed=True,
            ),
        )
        stack.recorder.record_authorization_grant(grant(), ActorCall("user-1", None))
        first = stack.tool.call(request())
        stack.recorder.record_authorization_revocation("grant-1", ActorCall("user-1", None))

        # When: 撤销后再次请求同一 Effect
        second = stack.tool.call(request().model_copy(update={"action_id": "read-again"}))

        # Then: 历史 Effect 保持执行，后续请求带 GRANT_REVOKED 被阻断
        assert isinstance(first, ExecutedToolCall)
        assert isinstance(second, DeniedToolCall)
        assert second.decision.reason_codes == (PolicyReasonCode.GRANT_REVOKED.value,)
        assert len(store.iter_run_effects("run-1")) == 1
