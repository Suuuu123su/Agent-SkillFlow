"""声明式 Scenario 的 T05 编排入口。"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import assert_never

from skillflow.adapters.base import (
    HarnessSession,
    SkillBinding,
    SkillInvocation,
    SkillInvocationResult,
)
from skillflow.adapters.mock_harness import (
    BenchmarkController,
    MockHarnessAdapter,
    MockHarnessConfig,
)
from skillflow.benchmark.scripted_backend import FixtureScript, ScriptedBackend
from skillflow.instrumentation.errors import UnsupportedStepError, WorkspaceEscapeError
from skillflow.instrumentation.mock_tools import MockNetworkRecord, MockShellRecord
from skillflow.instrumentation.tool_proxy import StubDecisionProvider
from skillflow.instrumentation.tool_receipt import ToolReceipt
from skillflow.models.enums import Decision
from skillflow.models.provenance import Artifact
from skillflow.models.scenario import Scenario
from skillflow.models.scenario_parts import ScenarioStep, StepAction
from skillflow.runtime.determinism import DeterministicIdFactory, VirtualClock
from skillflow.runtime.session import RuntimeDependencies
from skillflow.store.blob_store import RunBlobStore
from skillflow.store.sqlite_store import SqliteEventStore
from skillflow.store.trace import RunTrace, build_run_trace
from skillflow.validation import validate_yaml_document


@dataclass(frozen=True, slots=True)
class ScenarioRunResult:
    """一次 Scenario 运行的可观察结果。"""

    scenario_id: str
    run_id: str
    trace: RunTrace
    receipts: tuple[ToolReceipt, ...]
    output_artifacts: tuple[Artifact, ...]
    network_records: tuple[MockNetworkRecord, ...]
    shell_records: tuple[MockShellRecord, ...]
    workspace_root: Path
    database_path: Path


class ScenarioRunner:
    """把已校验 Scenario 驱动到 Mock Harness。"""

    def __init__(
        self,
        scripts: Mapping[str, FixtureScript],
        decisions: Mapping[str, Decision],
    ) -> None:
        """复制白名单脚本和 Stub 决策，隔离调用方后续修改。"""
        self._scripts = dict(scripts)
        self._decisions = dict(decisions)

    def run(self, scenario_path: Path, run_root: Path, seed: str) -> ScenarioRunResult:
        """从 YAML 启动一个独立、确定性的安全 Mock Run。"""
        scenario = validate_yaml_document(scenario_path, Scenario)
        run_root.mkdir(parents=True, exist_ok=False)
        workspace = run_root / "workspace"
        workspace.mkdir()
        self._stage_assets(scenario, workspace)
        run_id = f"run-{scenario.id}"
        database = run_root / "state.sqlite"
        outputs: list[Artifact] = []
        receipts: list[ToolReceipt] = []
        with (
            SqliteEventStore(database) as store,
            RunBlobStore(run_root, run_id) as blobs,
        ):
            harness = MockHarnessAdapter(
                MockHarnessConfig(
                    run_id=run_id,
                    task_id=scenario.task.id,
                    workspace_root=workspace,
                    dependencies=RuntimeDependencies(
                        event_store=store,
                        blob_store=blobs,
                        clock=VirtualClock(scenario.clock.start),
                        id_factory=DeterministicIdFactory(seed),
                    ),
                ),
                ScriptedBackend(self._scripts),
                StubDecisionProvider(self._decisions),
            )
            controller = BenchmarkController(harness)
            bindings = {
                skill.id: SkillBinding(skill.id, skill.implementation) for skill in scenario.skills
            }
            for session in scenario.sessions:
                harness.start_session(HarnessSession(session.id))
                try:
                    invoked_skills = tuple(
                        dict.fromkeys(
                            step.skill
                            for step in session.steps
                            if step.action is StepAction.INVOKE_SKILL and step.skill is not None
                        )
                    )
                    for skill_id in invoked_skills:
                        harness.load_skill(bindings[skill_id])
                    for step in session.steps:
                        result = self._execute_step(step, harness, controller)
                        if result is not None:
                            outputs.append(result.output)
                            receipts.extend(result.receipts)
                finally:
                    harness.end_session()
            trace = build_run_trace(store, run_id)
            network_records = harness.network_records
            shell_records = harness.shell_records
        return ScenarioRunResult(
            scenario_id=scenario.id,
            run_id=run_id,
            trace=trace,
            receipts=tuple(receipts),
            output_artifacts=tuple(outputs),
            network_records=network_records,
            shell_records=shell_records,
            workspace_root=workspace,
            database_path=database,
        )

    @staticmethod
    def _execute_step(
        step: ScenarioStep,
        harness: MockHarnessAdapter,
        controller: BenchmarkController,
    ) -> SkillInvocationResult | None:
        match step.action:
            case StepAction.INVOKE_SKILL:
                if step.skill is None:
                    raise UnsupportedStepError(step.id, "invoke_skill without skill")
                return harness.invoke_skill(SkillInvocation(step.skill))
            case StepAction.REVOKE_SKILL:
                if step.skill is None or step.actor is None:
                    raise UnsupportedStepError(step.id, "invalid revoke_skill")
                controller.revoke_skill(step.skill, step.actor)
                return None
            case StepAction.UNLOAD_SKILL:
                if step.skill is None or step.actor is None:
                    raise UnsupportedStepError(step.id, "invalid unload_skill")
                controller.unload_skill(step.skill, step.actor)
                return None
            case StepAction.USER_CONFIRM:
                if step.actor is None:
                    raise UnsupportedStepError(step.id, "invalid user_confirm")
                controller.confirm_tool(step.id, step.actor)
                return None
            case (
                StepAction.WRITE_MEMORY
                | StepAction.READ_MEMORY
                | StepAction.REQUEST_TOOL
                | StepAction.RESTART_RUNTIME
            ):
                raise UnsupportedStepError(step.id, step.action.value)
            case _ as unreachable:
                assert_never(unreachable)

    @staticmethod
    def _stage_assets(scenario: Scenario, workspace: Path) -> None:
        """把 fixture marker 复制到本次 Run 独占 Workspace。"""
        for asset in scenario.assets:
            prefix = "fixture://"
            if not asset.uri.root.startswith(prefix):
                raise UnsupportedStepError(asset.id, "T05 assets require fixture://")
            target = (workspace / asset.uri.root.removeprefix(prefix)).resolve()
            if not target.is_relative_to(workspace.resolve()):
                raise WorkspaceEscapeError(asset.uri.root)
            target.parent.mkdir(parents=True, exist_ok=True)
            content = asset.marker if asset.marker is not None else asset.id
            target.write_text(content, encoding="utf-8")
