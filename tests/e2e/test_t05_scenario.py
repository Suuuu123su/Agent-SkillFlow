from pathlib import Path

from skillflow.benchmark.runner import ScenarioRunner
from skillflow.benchmark.scripted_backend import FixtureScript, ToolScriptAction
from skillflow.instrumentation.tool_types import ReadFileArgs
from skillflow.models.enums import Decision, EventType
from skillflow.models.resources import ResourceRef


def make_runner() -> ScenarioRunner:
    script = FixtureScript(
        output=b"fixture completed",
        actions=(
            ToolScriptAction(
                action_id="read-report",
                decision_key="allow-report-read",
                arguments=ReadFileArgs(resource=ResourceRef("workspace:/documents/report.txt")),
            ),
        ),
    )
    return ScenarioRunner(
        scripts={"fixture://benign_reader": script},
        decisions={"allow-report-read": Decision.ALLOW},
    )


def test_benign_yaml_scenario_runs_to_tool_receipt_without_external_effects(
    tmp_path: Path,
) -> None:
    # Given: 一个只引用白名单 fixture 的良性 YAML Scenario
    scenario = Path(__file__).parents[1] / "fixtures" / "t05" / "benign_read.yaml"

    # When: 从 YAML 驱动完整 Mock Harness
    result = make_runner().run(scenario, tmp_path / "first", seed="stable-seed")

    # Then: 运行到强类型 Receipt，且网络与 Shell 均没有真实或 Mock 发送记录
    assert len(result.receipts) == 1
    assert result.network_records == ()
    assert result.shell_records == ()
    assert EventType.TOOL_CALL_RESULT in {event.event_type for event in result.trace.events}
    assert result.trace.trace_hash


def test_same_seed_is_deterministic_and_runs_are_isolated(tmp_path: Path) -> None:
    # Given: 同一个 Runner、同一个 YAML 与相同 seed
    scenario = Path(__file__).parents[1] / "fixtures" / "t05" / "benign_read.yaml"
    runner = make_runner()

    # When: 在两个独立 Run 根目录执行
    first = runner.run(scenario, tmp_path / "first", seed="stable-seed")
    second = runner.run(scenario, tmp_path / "second", seed="stable-seed")

    # Then: Trace 完全可复现，且文件、Context/Receipt 累积状态不跨 Run 泄漏
    assert first.trace.trace_hash == second.trace.trace_hash
    assert first.workspace_root != second.workspace_root
    assert len(first.receipts) == len(second.receipts) == 1
    assert first.output_artifacts[0].artifact_id == second.output_artifacts[0].artifact_id
