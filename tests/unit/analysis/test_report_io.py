from pathlib import Path

import pytest

from skillflow.analysis.errors import RiskReportWriteError
from skillflow.analysis.facts import ScenarioMetricFacts
from skillflow.analysis.report_io import write_run_risk_report
from skillflow.analysis.reporting import analyze_scenario


def test_risk_report_writer_never_overwrites_existing_file(tmp_path: Path) -> None:
    target = tmp_path / "risk-report.json"
    sentinel = b"existing report\n"
    target.write_bytes(sentinel)
    report = analyze_scenario(
        ScenarioMetricFacts(
            scenario_id="scenario-1",
            run_id="run-1",
            effects=(),
            provenance=(),
        )
    )

    with pytest.raises(RiskReportWriteError) as captured:
        write_run_risk_report(target, report)

    assert captured.value.path == target
    assert target.read_bytes() == sentinel
