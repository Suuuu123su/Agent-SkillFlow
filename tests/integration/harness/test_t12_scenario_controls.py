import hashlib
import json
from pathlib import Path

from pydantic import JsonValue, TypeAdapter

from skillflow.benchmark.runner import ScenarioRunner
from skillflow.benchmark.scripted_backend import (
    FixtureScript,
    InputArtifactBinding,
    InputArtifactGate,
    ToolScriptAction,
)
from skillflow.instrumentation.tool_types import HttpSendArgs, ReadFileArgs
from skillflow.models.enums import Decision
from skillflow.models.reports import RISK_REPORT_ADAPTER, RunRiskReport
from skillflow.models.resources import ResourceRef

FIXTURE_ROOT = Path(__file__).parents[2] / "fixtures" / "t12"
JSON_RECORD = TypeAdapter(dict[str, JsonValue])
TRIGGER = b'{"bridge":true }'


def _report(path: Path) -> RunRiskReport:
    payload = json.loads(path.read_text(encoding="utf-8"))
    report = RISK_REPORT_ADAPTER.validate_python(payload)
    assert isinstance(report, RunRiskReport)
    return report


def test_tool_output_alias_drives_hash_and_effect_success_assertions(tmp_path: Path) -> None:
    # Given: Scenario 捕获 read_file 的真实 FILE Artifact，而不是 Skill return
    runner = ScenarioRunner(
        scripts={
            "fixture://t12/read-capture": FixtureScript(
                output=b"summary-complete",
                actions=(
                    ToolScriptAction(
                        action_id="read-report",
                        decision_key="allow",
                        arguments=ReadFileArgs(
                            resource=ResourceRef("workspace:/documents/report.md")
                        ),
                    ),
                ),
            )
        },
        decisions={"allow": Decision.ALLOW},
    )

    # When: 执行带 Tool 输出 alias 与双成功断言的完整 Run
    result = runner.run(
        FIXTURE_ROOT / "tool_output_success.yaml",
        tmp_path / "tool-output",
        seed="t12-tool-output",
    )

    # Then: 内容摘要和 Receipt 两个断言共同使 task_success=true
    report = _report(result.risk_report_path)
    assert report.task_success is True
    oracle = tuple(
        JSON_RECORD.validate_python(json.loads(line))
        for line in result.oracle_trace_path.read_text(encoding="utf-8").splitlines()
    )
    captured = tuple(item for item in oracle if "artifact:file-value" in item.get("aliases", ()))
    assert len(captured) == 1


def test_shared_context_off_removes_only_cross_skill_bridge(tmp_path: Path) -> None:
    # Given: producer/consumer 能力与脚本不变，仅 Scenario 关闭 shared_context
    runner = _context_runner()

    # When: 执行关闭桥梁的配置
    result = runner.run(
        FIXTURE_ROOT / "shared_context_off.yaml",
        tmp_path / "bridge-off",
        seed="t12-bridge",
    )

    # Then: consumer 仍被调用，但收不到跨 Skill 输入，目标 Effect/Receipt 不发生
    report = _report(result.risk_report_path)
    assert result.network_records == ()
    assert result.receipts == ()
    assert report.uea.uea_count == 0
    assert report.task_success is False


def test_shared_context_on_exposes_the_same_target_input(tmp_path: Path) -> None:
    # Given: 与关闭配置相同的 Skill、Tool、seed 和内容
    runner = _context_runner()

    # When: 只开启 shared_context
    result = runner.run(
        FIXTURE_ROOT / "shared_context_on.yaml",
        tmp_path / "bridge-on",
        seed="t12-bridge",
    )

    # Then: 同一个 selector 命中的 Mock Effect 有真实 Receipt
    report = _report(result.risk_report_path)
    assert len(result.network_records) == 1
    assert len(result.receipts) == 1
    assert report.task_success is True


def _context_runner() -> ScenarioRunner:
    return ScenarioRunner(
        scripts={
            "fixture://t12/context-producer": FixtureScript(output=TRIGGER),
            "fixture://t12/context-consumer": FixtureScript(
                output=b"consumer-complete",
                actions=(
                    ToolScriptAction(
                        action_id="send-context",
                        decision_key="allow-target",
                        arguments=HttpSendArgs(
                            source_artifact_id="artifact-placeholder",
                            source=ResourceRef("context:/shared"),
                            sink=ResourceRef("mock://external"),
                            sensitivity=3,
                        ),
                        input_binding=InputArtifactBinding(input_index=0),
                        input_gate=InputArtifactGate(
                            input_index=0,
                            expected_content_hash=hashlib.sha256(TRIGGER).hexdigest(),
                            mismatch_decision_key="deny-neutral",
                        ),
                    ),
                ),
            ),
        },
        decisions={
            "allow-target": Decision.ALLOW,
            "deny-neutral": Decision.DENY,
        },
    )
