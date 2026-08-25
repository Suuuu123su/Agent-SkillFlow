"""标准风险报告的读取、Schema 复验与原子更新。"""

from pathlib import Path

from pydantic import ValidationError

from skillflow.experiment.errors import (
    CommandExitCode,
    ExperimentCommandError,
    ExperimentErrorCode,
)
from skillflow.experiment.io import replace_json_model, write_json_model
from skillflow.models.reports import RISK_REPORT_ADAPTER, RiskReport


def read_risk_report(path: Path) -> RiskReport:
    """读取并按 report_scope 判别 Schema。"""
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ExperimentCommandError(
            ExperimentErrorCode.RESOURCE_NOT_FOUND,
            f"报告不存在：{path.name}",
            CommandExitCode.NOT_FOUND,
        ) from error
    try:
        return RISK_REPORT_ADAPTER.validate_json(content)
    except ValidationError as error:
        raise ExperimentCommandError(
            ExperimentErrorCode.EXECUTION_FAILED,
            f"报告不符合风险报告 Schema：{path.name}",
            CommandExitCode.EXECUTION_FAILED,
        ) from error


def replace_risk_report(path: Path, report: RiskReport) -> None:
    """Schema 复验后原子更新派生报告。"""
    validated = RISK_REPORT_ADAPTER.validate_python(report.model_dump(mode="json", by_alias=True))
    replace_json_model(path, validated)


def export_risk_report(path: Path, report: RiskReport) -> None:
    """Schema 复验后不可覆盖导出。"""
    validated = RISK_REPORT_ADAPTER.validate_python(report.model_dump(mode="json", by_alias=True))
    write_json_model(path, validated)
