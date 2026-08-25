import json
from pathlib import Path

from jsonschema import Draft202012Validator

from skillflow.benchmark.runner import ScenarioRunner
from skillflow.benchmark.scripted_backend import FixtureScript, ToolScriptAction
from skillflow.instrumentation.tool_types import ReadFileArgs
from skillflow.models.enums import Decision
from skillflow.models.reports import RISK_REPORT_ADAPTER, RunRiskReport
from skillflow.models.resources import ResourceRef
from skillflow.policy.reasons import PolicyReasonCode

FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "t08"


def test_monitor_run_writes_schema_valid_t09_risk_report(tmp_path: Path) -> None:
    # Given: baseline 执行、Oracle 判定无有效 Grant 的 monitor 场景
    runner = ScenarioRunner(
        scripts={
            "fixture://benign_reader": FixtureScript(
                output=b"fixture completed",
                actions=(
                    ToolScriptAction(
                        action_id="read-report",
                        decision_key="read-report",
                        arguments=ReadFileArgs(
                            resource=ResourceRef("workspace:/documents/report.txt")
                        ),
                    ),
                ),
            )
        },
        decisions={"read-report": Decision.ALLOW},
    )

    # When: 完整运行 Scenario
    result = runner.run(
        FIXTURE_ROOT / "monitor_missing_grant.yaml",
        tmp_path / "run",
        seed="t09-risk-report",
    )
    content = result.risk_report_path.read_text(encoding="utf-8")
    payload = json.loads(content)
    report = RISK_REPORT_ADAPTER.validate_python(payload)
    schema = json.loads(Path("schemas/risk-report.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(payload)

    # Then: 报告以真实 Receipt 计一个 UEA，并附理由、路径和证据 ID
    assert isinstance(report, RunRiskReport)
    assert report.uea.uea_count == 1
    assert report.uea.uea_type_count == 1
    unauthorized = report.unauthorized_effects[0]
    assert unauthorized.reason_codes == (PolicyReasonCode.USER_GRANT_MISSING,)
    assert unauthorized.paths
    assert unauthorized.evidence_ids

    # And: 来源比例不是孤立浮点数，保留分子、分母和 Artifact/Event 证据
    precision = report.provenance.overall.precision
    assert precision.denominator > 0
    assert precision.value == precision.numerator / precision.denominator
    assert precision.evidence_ids

    # And: 风险报告不复制 fixture 输入或 Skill 输出正文
    assert "T08_MONITOR_MARKER" not in content
    assert "fixture completed" not in content
