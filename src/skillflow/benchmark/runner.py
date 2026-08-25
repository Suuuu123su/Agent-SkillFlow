"""声明式 Scenario 的确定性编排入口。"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from skillflow.analysis.facts import RunReportMetadata
from skillflow.analysis.run_reporting import RunTraceAnalysisInput, write_analyzed_run_report
from skillflow.benchmark.harness_factory import HarnessFactorySetup, create_scenario_harness
from skillflow.benchmark.manifests import load_manifests
from skillflow.benchmark.oracle_bridge import OracleSetup, build_oracle_sidecar
from skillflow.benchmark.run_facts import (
    load_effect_analysis_evidence,
    load_run_revocations,
)
from skillflow.benchmark.run_workspace import stage_assets
from skillflow.benchmark.scenario_execution import execute_scenario_sessions
from skillflow.benchmark.scripted_backend import FixtureScript
from skillflow.benchmark.success import TaskSuccessFacts, evaluate_task_success
from skillflow.graph.security import SecurityGraph
from skillflow.instrumentation.mock_tools import MockNetworkRecord, MockShellRecord
from skillflow.instrumentation.tool_receipt import ToolReceipt
from skillflow.models.enums import Decision
from skillflow.models.provenance import Artifact
from skillflow.models.reports import RunRiskReport
from skillflow.models.scenario import Scenario
from skillflow.oracle.writer import OracleTraceWriter
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
    artifact_ids_by_alias: dict[str, str]
    network_records: tuple[MockNetworkRecord, ...]
    shell_records: tuple[MockShellRecord, ...]
    workspace_root: Path
    database_path: Path
    observed_trace_path: Path
    oracle_trace_path: Path
    security_graph_path: Path
    risk_report_path: Path
    risk_report: RunRiskReport


@dataclass(frozen=True, slots=True)
class ScenarioRunLayout:
    """一次 Run 的事实库、受控内容与派生产物路径。"""

    run_root: Path
    experiment_root: Path
    database_path: Path
    workspace_root: Path
    security_graph_path: Path
    risk_report_path: Path


@dataclass(frozen=True, slots=True)
class ScenarioRunRequest:
    """已校验 Scenario 的完整 T13 执行请求。"""

    scenario_path: Path
    scenario: Scenario
    run_id: str
    id_seed: str
    layout: ScenarioRunLayout
    report_metadata: RunReportMetadata = field(default_factory=RunReportMetadata)


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
        run_id = f"run-{scenario.id}"
        return self.run_configured(
            ScenarioRunRequest(
                scenario_path=scenario_path,
                scenario=scenario,
                run_id=run_id,
                id_seed=seed,
                layout=ScenarioRunLayout(
                    run_root=run_root,
                    experiment_root=run_root,
                    database_path=run_root / "state.sqlite",
                    workspace_root=run_root / "workspace",
                    security_graph_path=run_root / "security-graph.json",
                    risk_report_path=run_root / "risk-report.json",
                ),
            )
        )

    def run_configured(self, request: ScenarioRunRequest) -> ScenarioRunResult:
        """执行一个具有显式 Run ID、共享事实库和报告身份的 Scenario。"""
        scenario_path = request.scenario_path
        scenario = request.scenario
        manifest_bindings = load_manifests(scenario_path, scenario)
        run_id = request.run_id
        oracle = build_oracle_sidecar(
            OracleSetup(
                scenario_path=scenario_path,
                scenario=scenario,
                run_id=run_id,
                scripts=self._scripts,
            )
        )
        layout = request.layout
        run_root = layout.run_root
        run_root.mkdir(parents=True, exist_ok=False)
        workspace = layout.workspace_root
        workspace.parent.mkdir(parents=True, exist_ok=True)
        workspace.mkdir()
        stage_assets(scenario, workspace)
        database = layout.database_path
        observed_trace_path = run_root / "observed-trace.jsonl"
        oracle_trace_path = run_root / "oracle-trace.jsonl"
        security_graph_path = layout.security_graph_path
        risk_report_path = layout.risk_report_path
        with (
            SqliteEventStore(database) as store,
            RunBlobStore(layout.experiment_root, run_id) as blobs,
        ):
            harness = create_scenario_harness(
                HarnessFactorySetup(
                    scenario=scenario,
                    run_id=run_id,
                    workspace=workspace,
                    event_store=store,
                    blob_store=blobs,
                    scripts=self._scripts,
                    decisions=self._decisions,
                    manifests=manifest_bindings,
                    seed=request.id_seed,
                )
            )
            execution = execute_scenario_sessions(scenario, harness, oracle)
            alias_artifacts = tuple(
                artifact
                for artifact_id in execution.artifact_ids_by_alias.values()
                if (artifact := store.get_artifact(artifact_id)) is not None
            )
            task_success = evaluate_task_success(
                TaskSuccessFacts(
                    scenario=scenario,
                    artifact_ids_by_alias=execution.artifact_ids_by_alias,
                    artifacts=alias_artifacts,
                    effects=store.iter_run_effects(run_id),
                    receipts=execution.receipts,
                )
            )
            oracle_records = oracle.finalize()
            OracleTraceWriter(oracle_trace_path).write(oracle_records)
            observed_records = ObservedTraceWriter(observed_trace_path).write(
                ObservedRunInput(
                    run_id=run_id,
                    store=store,
                    receipts=execution.receipts,
                    artifact_aliases=execution.artifact_aliases,
                )
            )
            trace = build_run_trace(store, run_id)
            graph = SecurityGraph.from_store(store, run_id)
            graph.export_json(security_graph_path)
            effects = store.iter_run_effects(run_id)
            report = write_analyzed_run_report(
                risk_report_path,
                RunTraceAnalysisInput(
                    scenario_id=scenario.id,
                    run_id=run_id,
                    observed_records=observed_records,
                    oracle_records=oracle_records,
                    graph=graph,
                    task_success=task_success,
                    scenario_definition=scenario,
                    metadata=request.report_metadata,
                    effect_evidence=load_effect_analysis_evidence(store, effects),
                    runtime_artifacts=alias_artifacts,
                    revocations=load_run_revocations(store, scenario, run_id),
                ),
            )
            network_records = harness.network_records
            shell_records = harness.shell_records
        return ScenarioRunResult(
            scenario_id=scenario.id,
            run_id=run_id,
            trace=trace,
            receipts=execution.receipts,
            output_artifacts=execution.output_artifacts,
            artifact_ids_by_alias=execution.artifact_ids_by_alias,
            network_records=network_records,
            shell_records=shell_records,
            workspace_root=workspace,
            database_path=database,
            observed_trace_path=observed_trace_path,
            oracle_trace_path=oracle_trace_path,
            security_graph_path=security_graph_path,
            risk_report_path=risk_report_path,
            risk_report=report,
        )
