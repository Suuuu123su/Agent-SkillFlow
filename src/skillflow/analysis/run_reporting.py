"""一次 Run 的 T09 投影、计算与报告写入门面。"""

from pathlib import Path

from skillflow.analysis.projection import (
    RunTraceAnalysisInput,
    project_scenario_facts,
)
from skillflow.analysis.report_io import write_run_risk_report
from skillflow.analysis.reporting import analyze_scenario

__all__ = ["RunTraceAnalysisInput", "write_analyzed_run_report"]


def write_analyzed_run_report(path: Path, run: RunTraceAnalysisInput) -> None:
    """保持投影、纯计算、Schema 校验写入的固定顺序。"""
    facts = project_scenario_facts(run)
    report = analyze_scenario(facts)
    write_run_risk_report(path, report)
