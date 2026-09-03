"""T13 Matrix 的离线执行、重放、确定性检查与聚合编排。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from skillflow.analysis.report_io import write_experiment_risk_report
from skillflow.benchmark.replay import ReplayRunner
from skillflow.benchmark.runner import (
    ScenarioHarnessFactory,
    ScenarioRunner,
    ScenarioRunRequest,
)
from skillflow.benchmark.t12_fixtures import t12_fixture_registry
from skillflow.experiment.aggregation import StandardAggregationInput, aggregate_standard_results
from skillflow.experiment.errors import (
    CommandExitCode,
    ExperimentCommandError,
    ExperimentErrorCode,
)
from skillflow.experiment.inputs import (
    apply_variant,
    namespace_grants,
    safe_output_id,
    scenario_reference,
    selected_harm_selector,
    slug,
)
from skillflow.experiment.io import write_json_model, write_summary_csv
from skillflow.experiment.layout import ExperimentLayout
from skillflow.experiment.matrix_determinism import check_determinism
from skillflow.experiment.matrix_replays import run_matrix_replays
from skillflow.experiment.matrix_support import (
    ExecutedVariant,
    MatrixRunObserver,
    build_run_metadata,
)
from skillflow.experiment.run_artifacts import (
    RunArtifactRequest,
    require_mock_only,
    write_run_manifest,
)
from skillflow.models.execution import (
    DeterminismCheck,
    ExecutionBackend,
    ExperimentKind,
    ExperimentManifest,
)
from skillflow.models.scenario import Scenario
from skillflow.validation import validate_yaml_document

if TYPE_CHECKING:
    from skillflow.models.matrix import ExperimentMatrix, ExperimentVariant
    from skillflow.models.reports import ReplayRiskReport, RunRiskReport
    from skillflow.models.scenario_parts import EffectSelector


@dataclass(frozen=True, slots=True)
class MatrixExecutionRequest:
    """CLI Matrix 命令的强类型执行参数。"""

    matrix_path: Path
    matrix: ExperimentMatrix
    output: Path | None
    determinism_repeats: int | None
    redacted: bool
    kind: ExperimentKind = ExperimentKind.MATRIX
    source: str | None = None
    harness_factory: ScenarioHarnessFactory | None = None
    run_observer: MatrixRunObserver | None = None
    replay_variants: frozenset[str] | None = None


@dataclass(frozen=True, slots=True)
class MatrixExecutionOutcome:
    """Matrix 成功消息所需的稳定结果。"""

    experiment_id: str
    run_count: int
    replay_count: int
    output_root: Path


def execute_matrix(request: MatrixExecutionRequest) -> MatrixExecutionOutcome:
    """执行核心 Run、确定性副本、反事实与标准报告聚合。"""
    if request.replay_variants is not None and not request.replay_variants.issubset(
        {item.variant for item in request.matrix.variants}
    ):
        raise ValueError("matrix_replay_variant_unknown")
    repeats = request.matrix.determinism_repeats
    if request.determinism_repeats is not None:
        repeats = request.determinism_repeats
    if repeats < 1:
        raise ExperimentCommandError(
            ExperimentErrorCode.INPUT_VALUE_INVALID,
            "determinism-repeats 必须至少为 1",
            CommandExitCode.INPUT_INVALID,
        )
    root = Path("runs") / request.matrix.id if request.output is None else request.output
    experiment_id = safe_output_id(root)
    layout = ExperimentLayout.create(root)
    scripts, decisions = t12_fixture_registry()
    runner = ScenarioRunner(scripts, decisions, request.harness_factory)
    replay_runner = ReplayRunner(scripts, decisions, request.harness_factory)
    executed: list[ExecutedVariant] = []
    run_reports: list[RunRiskReport] = []
    replay_reports: list[ReplayRiskReport] = []
    checks: list[DeterminismCheck] = []
    for variant in request.matrix.variants:
        item = _run_variant(layout, experiment_id, variant, request.redacted, runner)
        if request.run_observer is not None:
            request.run_observer(item)
        executed.append(item)
        run_reports.append(item.result.risk_report)
        checks.append(check_determinism(item, layout, experiment_id, repeats, runner))
        if request.replay_variants is None or variant.variant in request.replay_variants:
            replay_reports.extend(
                run_matrix_replays(item, layout, experiment_id, request.redacted, replay_runner)
            )
    selector = _fallback_selector(request.matrix, tuple(executed))
    report = aggregate_standard_results(
        StandardAggregationInput(
            experiment_id=experiment_id,
            runs=tuple(run_reports),
            replays=tuple(replay_reports),
            fallback_selector=selector,
        )
    )
    write_experiment_risk_report(layout.root / "aggregate-metrics.json", report)
    write_experiment_risk_report(layout.root / "experiment-report.json", report)
    write_summary_csv(layout.root / "summary.csv", tuple(run_reports), report)
    write_json_model(
        layout.root / "experiment-manifest.json",
        ExperimentManifest(
            experiment_id=experiment_id,
            kind=request.kind,
            source=request.source or scenario_reference(request.matrix_path).root,
            backend=ExecutionBackend.SCRIPTED,
            redacted=request.redacted,
            determinism_repeats=repeats,
            run_ids=tuple(item.result.run_id for item in executed),
            replay_ids=tuple(replay.replay_id for replay in replay_reports),
            determinism_checks=tuple(checks),
        ),
    )
    return MatrixExecutionOutcome(
        experiment_id,
        len(run_reports),
        len(replay_reports),
        layout.root,
    )


def _run_variant(
    layout: ExperimentLayout,
    experiment_id: str,
    variant: ExperimentVariant,
    redacted: bool,
    runner: ScenarioRunner,
) -> ExecutedVariant:
    scenario_path = Path(variant.scenario.root)
    run_id = f"run-{experiment_id}-{slug(variant.variant)}"
    scenario = namespace_grants(
        apply_variant(validate_yaml_document(scenario_path, Scenario), variant),
        run_id,
    )
    selector = variant.harm_selector or selected_harm_selector(scenario)
    result = runner.run_configured(
        ScenarioRunRequest(
            scenario_path=scenario_path,
            scenario=scenario,
            run_id=run_id,
            id_seed=f"{run_id}:{variant.seed}",
            layout=layout.run_layout(run_id),
            report_metadata=build_run_metadata(
                experiment_id,
                variant,
                selector if variant.harm_selector is not None or scenario.harm_selector else None,
                redacted,
            ),
        )
    )
    require_mock_only(result)
    write_run_manifest(
        RunArtifactRequest(layout, scenario_reference(scenario_path), result, redacted)
    )
    return ExecutedVariant(variant, scenario_path, scenario, result)


def _fallback_selector(
    matrix: ExperimentMatrix,
    executed: tuple[ExecutedVariant, ...],
) -> EffectSelector:
    if matrix.hiaa_design is not None:
        return matrix.hiaa_design.harm_selector
    if matrix.hiaa_designs:
        return matrix.hiaa_designs[0].harm_selector
    return selected_harm_selector(executed[0].scenario)
