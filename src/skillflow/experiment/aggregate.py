"""现有 Experiment 的标准结果重聚合。"""

from dataclasses import dataclass
from pathlib import Path
from typing import Never

from pydantic import ValidationError

from skillflow.experiment.aggregation import StandardAggregationInput, aggregate_standard_results
from skillflow.experiment.errors import (
    CommandExitCode,
    ExperimentCommandError,
    ExperimentErrorCode,
)
from skillflow.experiment.inputs import selected_harm_selector
from skillflow.experiment.io import replace_json_model, replace_summary_csv
from skillflow.experiment.locations import locate_experiment
from skillflow.experiment.report_store import read_risk_report, replace_risk_report
from skillflow.models.execution import ExperimentManifest
from skillflow.models.reports import ExperimentRiskReport, ReplayRiskReport, RunRiskReport
from skillflow.models.scenario import Scenario
from skillflow.models.scenario_parts import EffectSelector
from skillflow.validation import validate_yaml_document


@dataclass(frozen=True, slots=True)
class AggregateOutcome:
    """重聚合成功后的成员计数。"""

    experiment_id: str
    run_count: int
    replay_count: int
    output_root: Path


def aggregate_experiment(experiment_id: str, runs_root: Path) -> AggregateOutcome:
    """只扫描标准 Run/Replay 报告并更新 Experiment 派生物。"""
    root = locate_experiment(runs_root, experiment_id)
    manifest = _manifest(root / "experiment-manifest.json")
    runs = _run_reports(root)
    replays = _replay_reports(root)
    fallback = _fallback_selector(root, runs)
    report = aggregate_standard_results(
        StandardAggregationInput(experiment_id, runs, replays, fallback)
    )
    replace_risk_report(root / "aggregate-metrics.json", report)
    replace_risk_report(root / "experiment-report.json", report)
    replace_summary_csv(root / "summary.csv", runs, report)
    updated = manifest.model_copy(
        update={
            "run_ids": tuple(run.run_id for run in runs),
            "replay_ids": tuple(replay.replay_id for replay in replays),
        }
    )
    replace_json_model(root / "experiment-manifest.json", updated)
    return AggregateOutcome(experiment_id, len(runs), len(replays), root)


def _run_reports(root: Path) -> tuple[RunRiskReport, ...]:
    values: list[RunRiskReport] = []
    for directory in sorted((root / "runs").iterdir(), key=lambda path: path.name):
        report = read_risk_report(directory / "run-report.json")
        if not isinstance(report, RunRiskReport):
            _wrong_scope(directory / "run-report.json")
        values.append(report)
    return tuple(values)


def _replay_reports(root: Path) -> tuple[ReplayRiskReport, ...]:
    values: list[ReplayRiskReport] = []
    for directory in sorted((root / "replays").iterdir(), key=lambda path: path.name):
        report = read_risk_report(directory / "replay-report.json")
        if not isinstance(report, ReplayRiskReport):
            _wrong_scope(directory / "replay-report.json")
        values.append(report)
    return tuple(values)


def _fallback_selector(root: Path, runs: tuple[RunRiskReport, ...]) -> EffectSelector:
    current = read_risk_report(root / "experiment-report.json")
    if isinstance(current, ExperimentRiskReport):
        return current.harm_selector
    for run in runs:
        if run.harm_selector is not None:
            return run.harm_selector
        if run.scenario is not None:
            scenario = validate_yaml_document(Path(run.scenario.root), Scenario)
            return selected_harm_selector(scenario)
    raise ExperimentCommandError(
        ExperimentErrorCode.EXECUTION_FAILED,
        "Experiment 缺少可用的 harm_selector",
        CommandExitCode.EXECUTION_FAILED,
    )


def _manifest(path: Path) -> ExperimentManifest:
    try:
        return ExperimentManifest.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as error:
        raise ExperimentCommandError(
            ExperimentErrorCode.EXECUTION_FAILED,
            "experiment-manifest.json 缺失或无效",
            CommandExitCode.EXECUTION_FAILED,
        ) from error


def _wrong_scope(path: Path) -> Never:
    raise ExperimentCommandError(
        ExperimentErrorCode.EXECUTION_FAILED,
        f"报告层级错误：{path.name}",
        CommandExitCode.EXECUTION_FAILED,
    )
