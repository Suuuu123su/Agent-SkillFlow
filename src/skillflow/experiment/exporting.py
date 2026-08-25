"""标准 Run/Experiment 报告的 Schema 化导出。"""

from dataclasses import dataclass
from enum import StrEnum, unique
from pathlib import Path
from typing import Never

from skillflow.experiment.errors import (
    CommandExitCode,
    ExperimentCommandError,
    ExperimentErrorCode,
)
from skillflow.experiment.locations import locate_experiment, locate_run
from skillflow.experiment.report_store import export_risk_report, read_risk_report
from skillflow.models.reports import ExperimentRiskReport, RunRiskReport


@unique
class ExportScope(StrEnum):
    """报告导出的封闭层级。"""

    RUN = "run"
    EXPERIMENT = "experiment"


@dataclass(frozen=True, slots=True)
class ExportOutcome:
    """导出成功后的目标身份。"""

    scope: ExportScope
    identifier: str
    output: Path


def export_report(
    scope: ExportScope,
    identifier: str,
    output: Path,
    runs_root: Path,
    redacted: bool,
) -> ExportOutcome:
    """加载、复验并以不可覆盖方式导出标准报告。"""
    selected: RunRiskReport | ExperimentRiskReport
    if scope is ExportScope.RUN:
        located = locate_run(runs_root, identifier)
        report = read_risk_report(located.run_root / "run-report.json")
        if not isinstance(report, RunRiskReport):
            _wrong_scope(scope)
        selected = report.model_copy(update={"redacted": redacted})
    else:
        root = locate_experiment(runs_root, identifier)
        report = read_risk_report(root / "experiment-report.json")
        if not isinstance(report, ExperimentRiskReport):
            _wrong_scope(scope)
        selected = report
    export_risk_report(output, selected)
    return ExportOutcome(scope, identifier, output)


def _wrong_scope(scope: ExportScope) -> Never:
    raise ExperimentCommandError(
        ExperimentErrorCode.EXECUTION_FAILED,
        f"报告与请求 scope 不一致：{scope.value}",
        CommandExitCode.EXECUTION_FAILED,
    )
