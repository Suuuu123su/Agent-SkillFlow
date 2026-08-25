from datetime import UTC, datetime, timedelta
from pathlib import Path

from skillflow.adapters.base import HarnessSession, SkillBinding, SkillInvocation
from skillflow.adapters.mock_harness import (
    BenchmarkController,
    MockHarnessAdapter,
    MockHarnessConfig,
)
from skillflow.benchmark.scripted_backend import FixtureScript, ScriptedBackend, ToolScriptAction
from skillflow.instrumentation.decision_stub import StubDecisionProvider
from skillflow.models.authorization import AuthorizationGrant
from skillflow.models.enums import (
    CapabilityAction,
    Decision,
    Lifetime,
    PrincipalType,
    Scope,
)
from skillflow.models.references import FixtureImplementationRef
from skillflow.models.resources import ResourceRef
from skillflow.models.tool_calls import ShellExecArgs
from skillflow.runtime.determinism import DeterministicIdFactory, VirtualClock
from skillflow.runtime.session import RuntimeDependencies
from skillflow.store.blob_store import RunBlobStore
from skillflow.store.sqlite_store import SqliteEventStore

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _grant() -> AuthorizationGrant:
    return AuthorizationGrant(
        grant_id="grant-checkpoint",
        issuer_id="user-1",
        issuer_type=PrincipalType.USER,
        grantee_id="skill-a",
        action=CapabilityAction.SHELL_EXECUTE,
        source_pattern=None,
        sink_pattern=ResourceRef("mock://shell"),
        scope=Scope.COMMAND,
        lifetime=Lifetime.TASK,
        task_id="task-1",
        valid_from=NOW,
    )


def _harness(
    root: Path,
    run_id: str,
    store: SqliteEventStore,
    blobs: RunBlobStore,
) -> tuple[MockHarnessAdapter, VirtualClock]:
    workspace = root / "workspace"
    workspace.mkdir()
    clock = VirtualClock(NOW)
    harness = MockHarnessAdapter(
        MockHarnessConfig(
            run_id=run_id,
            task_id="task-1",
            workspace_root=workspace,
            dependencies=RuntimeDependencies(
                event_store=store,
                blob_store=blobs,
                clock=clock,
                id_factory=DeterministicIdFactory("checkpoint-seed"),
            ),
            initial_grants=(_grant(),),
        ),
        ScriptedBackend(
            {
                "fixture://skill-a": FixtureScript(
                    output=b"skill-output",
                    actions=(
                        ToolScriptAction(
                            action_id="mock-shell",
                            decision_key="allow-shell",
                            arguments=ShellExecArgs(command=("safe-mock", "--check")),
                        ),
                    ),
                )
            }
        ),
        StubDecisionProvider({"allow-shell": Decision.ALLOW}),
    )
    return harness, clock


def test_checkpoint_restores_full_runtime_into_an_isolated_branch(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    branch_root = tmp_path / "branch"
    source_root.mkdir()
    branch_root.mkdir()
    with (
        SqliteEventStore(source_root / "state.sqlite") as source_store,
        RunBlobStore(source_root, "run-source") as source_blobs,
        SqliteEventStore(branch_root / "state.sqlite") as branch_store,
        RunBlobStore(branch_root, "run-branch") as branch_blobs,
    ):
        source, source_clock = _harness(
            source_root,
            "run-source",
            source_store,
            source_blobs,
        )
        (source_root / "workspace" / "fixture.txt").write_bytes(b"workspace-state")
        source.start_session(HarnessSession("session-1"))
        source.load_skill(
            SkillBinding("skill-a", FixtureImplementationRef("fixture://skill-a"))
        )
        controller = BenchmarkController(source)
        context = controller.add_context(b"checkpoint-context", PrincipalType.USER)
        memory = controller.write_memory(
            "shared",
            context.artifact_id,
            PrincipalType.USER,
        )
        source.invoke_skill(SkillInvocation("skill-a"))
        source_clock.advance(timedelta(minutes=7))

        checkpoint = source.checkpoint()
        source_event_count = len(source_store.iter_run_events("run-source"))

        branch, _ = _harness(branch_root, "run-branch", branch_store, branch_blobs)
        branch.restore(checkpoint)
        restored = branch.checkpoint()

        assert restored.prefix_hash == checkpoint.prefix_hash
        assert restored.state_hash == checkpoint.state_hash
        assert restored.context.artifact_ids == (context.artifact_id,)
        assert restored.memory.entries == (("shared", memory.artifact_id),)
        assert restored.skills.loaded_skill_ids == ("skill-a",)
        assert restored.network_records == ()
        assert len(restored.shell_records) == 1
        assert restored.clock.current == NOW + timedelta(minutes=7)
        assert (branch_root / "workspace" / "fixture.txt").read_bytes() == b"workspace-state"
        assert branch_store.get_grant("grant-checkpoint") == _grant()
        assert branch_store.get_memory_head("run-branch", "shared") is not None
        assert {event.run_id for event in branch_store.iter_run_events("run-branch")} == {
            "run-branch"
        }

        source.invoke_skill(SkillInvocation("skill-a"))
        assert len(branch_store.iter_run_events("run-branch")) == checkpoint.event_count
        assert len(source_store.iter_run_events("run-source")) > source_event_count

        branch.end_session()
        source.end_session()
