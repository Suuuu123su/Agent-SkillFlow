"""声明式 Scenario 的确定性编排入口。"""

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
from skillflow.benchmark.manifests import load_manifests
from skillflow.benchmark.oracle_bridge import (
    OracleInvocationBinding,
    OracleSetup,
    build_oracle_sidecar,
    project_oracle_invocation,
)
from skillflow.benchmark.scripted_backend import FixtureScript, ScriptedBackend
from skillflow.graph.security import SecurityGraph
from skillflow.instrumentation.errors import UnsupportedStepError, WorkspaceEscapeError
from skillflow.instrumentation.mock_tools import MockNetworkRecord, MockShellRecord
from skillflow.instrumentation.tool_receipt import ToolReceipt
from skillflow.models.enums import Decision
from skillflow.models.provenance import Artifact
from skillflow.models.scenario import Scenario
from skillflow.models.scenario_parts import ScenarioStep, StepAction
from skillflow.oracle.writer import OracleTraceWriter
from skillflow.policy.runtime import RuntimePolicySetup, StoredPolicyDecisionProvider
from skillflow.runtime.determinism import DeterministicIdFactory, VirtualClock
from skillflow.runtime.session import RuntimeDependencies
from skillflow.store.blob_store import RunBlobStore
from skillflow.store.sqlite_store import SqliteEventStore
from skillflow.store.trace import RunTrace, build_run_trace
from skillflow.trace.observed import ObservedRunInput, ObservedTraceWriter
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
    observed_trace_path: Path
    oracle_trace_path: Path
    security_graph_path: Path


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
        manifest_bindings = load_manifests(scenario_path, scenario)
        run_id = f"run-{scenario.id}"
        oracle = build_oracle_sidecar(
            OracleSetup(
                scenario_path=scenario_path,
                scenario=scenario,
                run_id=run_id,
                scripts=self._scripts,
            )
        )
        run_root.mkdir(parents=True, exist_ok=False)
        workspace = run_root / "workspace"
        workspace.mkdir()
        self._stage_assets(scenario, workspace)
        database = run_root / "state.sqlite"
        observed_trace_path = run_root / "observed-trace.jsonl"
        oracle_trace_path = run_root / "oracle-trace.jsonl"
        security_graph_path = run_root / "security-graph.json"
        outputs: list[Artifact] = []
        receipts: list[ToolReceipt] = []
        artifact_aliases: dict[str, tuple[str, ...]] = {}
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
                        provenance_mode=scenario.harness.provenance_mode,
                    ),
                    initial_grants=scenario.grants,
                ),
                ScriptedBackend(self._scripts),
                StoredPolicyDecisionProvider(
                    store,
                    RuntimePolicySetup(
                        run_id=run_id,
                        manifests={
                            binding.skill_id: binding.manifest for binding in manifest_bindings
                        },
                        structural_decisions=self._decisions,
                        enforcement_mode=scenario.execution.mode,
                        auto_approve_tools=scenario.harness.auto_approve_tools,
                        implicit_text_authorization=(scenario.harness.implicit_text_authorization),
                    ),
                ),
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
                        if step.action is StepAction.USER_CONFIRM and step.grant is not None:
                            oracle.record_grant(step.grant)
                        if result is not None:
                            outputs.append(result.output)
                            receipts.extend(result.receipts)
                            aliases = tuple(output.root for output in step.outputs)
                            artifact_aliases[result.output.artifact_id] = aliases
                            oracle.record_invocation(
                                project_oracle_invocation(
                                    OracleInvocationBinding(
                                        step=step,
                                        session_id=session.id,
                                        result=result,
                                    )
                                )
                            )
                finally:
                    harness.end_session()
            oracle_records = oracle.finalize()
            OracleTraceWriter(oracle_trace_path).write(oracle_records)
            ObservedTraceWriter(observed_trace_path).write(
                ObservedRunInput(
                    run_id=run_id,
                    store=store,
                    receipts=tuple(receipts),
                    artifact_aliases=artifact_aliases,
                )
            )
            trace = build_run_trace(store, run_id)
            SecurityGraph.from_store(store, run_id).export_json(security_graph_path)
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
            observed_trace_path=observed_trace_path,
            oracle_trace_path=oracle_trace_path,
            security_graph_path=security_graph_path,
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
                if step.actor is None or step.grant is None:
                    raise UnsupportedStepError(step.id, "invalid user_confirm")
                controller.confirm_tool(step.grant, step.actor)
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
