"""风险报告的 Schema 校验与不可覆盖写入。"""

import json
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema import ValidationError as JsonSchemaValidationError

from skillflow.analysis.errors import AnalysisInvariantError, RiskReportWriteError
from skillflow.models.reports import RISK_REPORT_ADAPTER, RunRiskReport


def write_run_risk_report(path: Path, report: RunRiskReport) -> None:
    """先用模型生成 Schema 复验，再独占创建 JSON 报告。"""
    payload = report.model_dump(mode="json", by_alias=True)
    try:
        Draft202012Validator(RISK_REPORT_ADAPTER.json_schema()).validate(payload)
    except JsonSchemaValidationError as error:
        raise AnalysisInvariantError(
            "write_risk_report",
            f"模型与 JSON Schema 不一致：{error.message}",
        ) from error
    content = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.write("\n")
    except OSError as error:
        raise RiskReportWriteError(path, str(error)) from error
