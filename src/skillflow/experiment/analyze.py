"""从 SQLite 与双轨 JSONL 重建图和 RunResult。"""

from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

from pydantic import TypeAdapter, ValidationError

from skillflow.analysis.facts import RunReportMetadata
from skillflow.analysis.projection import RunTraceAnalysisInput, project_scenario_facts
from skillflow.analysis.reporting import analyze_scenario
from skillflow.benchmark.run_facts import (
    load_effect_analysis_evidence,
    load_run_revocations,
)
from skillflow.experiment.errors import (
    CommandExitCode,
    ExperimentCommandError,
    ExperimentErrorCode,
)
from skillflow.experiment.io import replace_json_model, sha256_file
from skillflow.experiment.locations import locate_run
from skillflow.experiment.report_store import read_risk_report, replace_risk_report
from skillflow.graph.security import SecurityGraph
from skillflow.models.execution import ArtifactDigest, RunManifest
from skillflow.models.reports import RunRiskReport
from skillflow.models.scenario import Scenario
from skillflow.oracle.models import OracleTraceRecord
from skillflow.store.sqlite_store import SqliteEventStore
from skillflow.trace.observed import ObservedTraceRecord
from skillflow.validation import validate_yaml_document

OBSERVED_ADAPTER: TypeAdapter[ObservedTraceRecord] = TypeAdapter(ObservedTraceRecord)
ORACLE_ADAPTER: TypeAdapter[OracleTraceRecord] = TypeAdapter(OracleTraceRecord)
RecordT = TypeVar("RecordT")


@dataclass(frozen=True, slots=True)
class AnalyzeOutcome:
    """重分析成功后的稳定路径。"""

    run_id: str
    report_path: Path


def analyze_persisted_run(run_id: str, runs_root: Path) -> AnalyzeOutcome:
    """不执行场景，直接从持久化事实重算 Run 派生物。"""
    located = locate_run(runs_root, run_id)
    old = read_risk_report(located.run_root / "run-report.json")
    if not isinstance(old, RunRiskReport) or old.scenario is None:
        raise ExperimentCommandError(
            ExperimentErrorCode.EXECUTION_FAILED,
            "run-report.json 缺少标准 Run 身份",
            CommandExitCode.EXECUTION_FAILED,
        )
    scenario = validate_yaml_document(Path(old.scenario.root), Scenario)
    observed = _jsonl(located.run_root / "observed-trace.jsonl", OBSERVED_ADAPTER)
    oracle = _jsonl(located.run_root / "oracle-trace.jsonl", ORACLE_ADAPTER)
    database = located.experiment_root / "state.sqlite"
    with SqliteEventStore(database) as store:
        effects = store.iter_run_effects(run_id)
        graph = SecurityGraph.from_store(store, run_id)
        artifacts = tuple(
            artifact
            for binding in old.counterfactual_artifacts
            if (artifact := store.get_artifact(binding.artifact_id)) is not None
        )
        report = analyze_scenario(
            project_scenario_facts(
                RunTraceAnalysisInput(
                    scenario_id=old.scenario_id,
                    run_id=run_id,
                    observed_records=observed,
                    oracle_records=oracle,
                    graph=graph,
                    task_success=old.task_success,
                    scenario_definition=scenario,
                    metadata=_metadata(old),
                    effect_evidence=load_effect_analysis_evidence(store, effects),
                    runtime_artifacts=artifacts,
                    revocations=load_run_revocations(store, scenario, run_id),
                )
            )
        )
    replace_json_model(located.run_root / "graph.json", graph.to_export())
    replace_risk_report(located.run_root / "run-report.json", report)
    _refresh_manifest(located.run_root)
    return AnalyzeOutcome(run_id, located.run_root / "run-report.json")


def _metadata(report: RunRiskReport) -> RunReportMetadata:
    return RunReportMetadata(
        experiment_id=report.experiment_id,
        scenario=report.scenario,
        variant=report.variant,
        seed=report.seed,
        backend=report.backend,
        latency_ms=report.latency_ms,
        harm_selector=report.harm_selector,
        hiaa_cell=report.hiaa_cell,
        hiaa_design_id=report.hiaa_design_id,
        pair_id=report.pair_id,
        run_role=report.run_role,
        skill_state=report.skill_state,
        session_condition=report.session_condition,
        authorization_condition=report.authorization_condition,
        shared_context=report.shared_context,
        persistent_memory=report.persistent_memory,
        auto_approve_tools=report.auto_approve_tools,
        enforcement_mode=report.enforcement_mode,
        provenance_mode=report.provenance_mode,
        implicit_text_authorization=report.implicit_text_authorization,
        redacted=report.redacted,
    )


def _jsonl(path: Path, adapter: TypeAdapter[RecordT]) -> tuple[RecordT, ...]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        return tuple(adapter.validate_json(line) for line in lines if line.strip())
    except (OSError, ValidationError) as error:
        raise ExperimentCommandError(
            ExperimentErrorCode.EXECUTION_FAILED,
            f"Trace 缺失或无效：{path.name}",
            CommandExitCode.EXECUTION_FAILED,
        ) from error


def _refresh_manifest(run_root: Path) -> None:
    path = run_root / "run-manifest.json"
    try:
        manifest = RunManifest.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as error:
        raise ExperimentCommandError(
            ExperimentErrorCode.EXECUTION_FAILED,
            "run-manifest.json 缺失或无效",
            CommandExitCode.EXECUTION_FAILED,
        ) from error
    outputs = (
        run_root / "observed-trace.jsonl",
        run_root / "oracle-trace.jsonl",
        run_root / "graph.json",
        run_root / "run-report.json",
    )
    artifacts = tuple(
        ArtifactDigest(name=output.name, sha256=sha256_file(output)) for output in outputs
    )
    replace_json_model(path, manifest.model_copy(update={"artifacts": artifacts}))
