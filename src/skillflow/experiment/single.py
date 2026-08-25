"""single-run Experiment 的离线编排。"""

from dataclasses import dataclass
from pathlib import Path

from skillflow.analysis.experiment_reporting import (
    ExperimentAggregationFacts,
    build_experiment_report,
)
from skillflow.analysis.facts import RunReportMetadata
from skillflow.analysis.report_io import write_experiment_risk_report
from skillflow.benchmark.runner import ScenarioRunner, ScenarioRunRequest
from skillflow.benchmark.t12_fixtures import t12_fixture_registry
from skillflow.experiment.errors import (
    CommandExitCode,
    ExperimentCommandError,
    ExperimentErrorCode,
)
from skillflow.experiment.inputs import (
    authorization_condition,
    safe_output_id,
    scenario_reference,
    selected_harm_selector,
    slug,
)
from skillflow.experiment.io import write_json_model, write_summary_csv
from skillflow.experiment.layout import ExperimentLayout
from skillflow.experiment.run_artifacts import (
    RunArtifactRequest,
    require_mock_only,
    write_run_manifest,
)
from skillflow.models.enums import EnforcementMode
from skillflow.models.execution import (
    ExecutionBackend,
    ExperimentKind,
    ExperimentManifest,
)
from skillflow.models.scenario import Scenario
from skillflow.validation import validate_yaml_document


@dataclass(frozen=True, slots=True)
class SingleRunOutcome:
    """CLI 成功消息所需的最小 Experiment 结果。"""

    experiment_id: str
    run_id: str
    output_root: Path


def execute_single_run(
    scenario_path: Path,
    mode: EnforcementMode,
    output: Path | None,
    redacted: bool,
) -> SingleRunOutcome:
    """运行一个 Scenario，并写出完整 single-run Experiment。"""
    scenario = validate_yaml_document(scenario_path, Scenario)
    scenario_ref = scenario_reference(scenario_path)
    selected = scenario.model_copy(
        update={"execution": scenario.execution.model_copy(update={"mode": mode})}
    )
    default_id = f"single-{slug(scenario.id)}"
    root = Path("runs") / default_id if output is None else output
    experiment_id = safe_output_id(root)
    layout = ExperimentLayout.create(root)
    run_id = f"run-{experiment_id}-single"
    harm_selector = selected_harm_selector(selected)
    scripts, decisions = t12_fixture_registry()
    result = ScenarioRunner(scripts, decisions).run_configured(
        ScenarioRunRequest(
            scenario_path=scenario_path,
            scenario=selected,
            run_id=run_id,
            id_seed=f"{run_id}:0",
            layout=layout.run_layout(run_id),
            report_metadata=RunReportMetadata(
                experiment_id=experiment_id,
                scenario=scenario_ref,
                variant="single",
                seed=0,
                backend=ExecutionBackend.SCRIPTED.value,
                latency_ms=0.0,
                harm_selector=harm_selector if selected.harm_selector is not None else None,
                pair_id=None if selected.pairing is None else selected.pairing.pair_id,
                authorization_condition=authorization_condition(selected),
                shared_context=selected.harness.shared_context,
                persistent_memory=selected.harness.persistent_memory,
                auto_approve_tools=selected.harness.auto_approve_tools,
                enforcement_mode=selected.execution.mode,
                provenance_mode=selected.harness.provenance_mode,
                implicit_text_authorization=selected.harness.implicit_text_authorization,
                redacted=redacted,
            ),
        )
    )
    require_mock_only(result)
    run_manifest = write_run_manifest(RunArtifactRequest(layout, scenario_ref, result, redacted))
    experiment_report = build_experiment_report(
        ExperimentAggregationFacts(
            experiment_id=experiment_id,
            run_ids=(run_id,),
            replay_ids=(),
            unauthorized_executed_count=result.risk_report.uea.uea_count,
            harm_selector=harm_selector,
            matrix_outcomes=(),
            harness_off_effects=(),
            harness_on_effects=(),
            authorization_attempts=(),
            revocation=None,
            residual_runs=(),
        )
    )
    write_experiment_risk_report(layout.root / "aggregate-metrics.json", experiment_report)
    write_experiment_risk_report(layout.root / "experiment-report.json", experiment_report)
    write_summary_csv(layout.root / "summary.csv", (result.risk_report,), experiment_report)
    write_json_model(
        layout.root / "experiment-manifest.json",
        ExperimentManifest(
            experiment_id=experiment_id,
            kind=ExperimentKind.SINGLE_RUN,
            source=scenario_ref.root,
            backend=ExecutionBackend.SCRIPTED,
            redacted=redacted,
            determinism_repeats=1,
            run_ids=(run_id,),
        ),
    )
    if not run_manifest.artifacts:
        raise ExperimentCommandError(
            ExperimentErrorCode.EXECUTION_FAILED,
            "Run 清单缺少派生产物摘要",
            CommandExitCode.EXECUTION_FAILED,
        )
    return SingleRunOutcome(experiment_id, run_id, layout.root)
