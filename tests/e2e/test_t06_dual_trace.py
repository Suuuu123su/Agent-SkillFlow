import json
from pathlib import Path

from pydantic import JsonValue, TypeAdapter

from skillflow.benchmark.runner import ScenarioRunner
from skillflow.benchmark.scripted_backend import FixtureScript, ToolScriptAction
from skillflow.instrumentation.tool_types import ReadFileArgs
from skillflow.models.enums import Decision
from skillflow.models.resources import ResourceRef

FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "t06"
T05_SCENARIO = Path(__file__).parents[1] / "fixtures" / "t05" / "benign_read.yaml"
JSON_RECORD = TypeAdapter(dict[str, JsonValue])


def make_runner(decision: Decision = Decision.ALLOW) -> ScenarioRunner:
    return ScenarioRunner(
        scripts={
            "fixture://benign_reader": FixtureScript(
                output=b"fixture completed",
                actions=(
                    ToolScriptAction(
                        action_id="read-report",
                        decision_key="allow-report-read",
                        arguments=ReadFileArgs(
                            resource=ResourceRef("workspace:/documents/report.txt")
                        ),
                    ),
                ),
            )
        },
        decisions={"allow-report-read": decision},
    )


def read_jsonl(path: Path) -> tuple[dict[str, JsonValue], ...]:
    return tuple(
        JSON_RECORD.validate_python(json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
    )


def by_record_type(
    records: tuple[dict[str, JsonValue], ...], record_type: str
) -> tuple[dict[str, JsonValue], ...]:
    return tuple(record for record in records if record["record_type"] == record_type)


def origin_recall(observed: set[str], oracle: set[str]) -> float:
    return len(observed & oracle) / len(oracle)


def test_scripted_run_writes_complete_aligned_observed_and_oracle_paths(
    tmp_path: Path,
) -> None:
    # Given: Manifest 与真实 Grant 都覆盖 read_file 的声明式场景
    scenario = FIXTURE_ROOT / "authorized_read.yaml"

    # When: 执行一次确定性 Mock Run
    result = make_runner().run(scenario, tmp_path / "run", seed="t06-seed")
    observed = read_jsonl(result.observed_trace_path)
    oracle = read_jsonl(result.oracle_trace_path)

    # Then: 双轨文件存在，且实际 Artifact/Effect 可按稳定 ID 对齐
    observed_artifacts = {
        str(record["artifact_id"]): record for record in by_record_type(observed, "artifact")
    }
    oracle_artifacts = {
        str(record["artifact_id"]): record for record in by_record_type(oracle, "artifact")
    }
    observed_effects = {
        str(record["effect_id"]): record for record in by_record_type(observed, "effect")
    }
    oracle_effects = {
        str(record["effect_id"]): record for record in by_record_type(oracle, "effect")
    }
    receipt = result.receipts[0]
    output_id = result.output_artifacts[0].artifact_id
    file_id = receipt.output_artifact_ids[0]

    assert observed_artifacts.keys() <= oracle_artifacts.keys()
    assert observed_effects.keys() == oracle_effects.keys()
    assert {
        file_id,
        receipt.argument_artifact_id,
        receipt.receipt_artifact_id,
        output_id,
    } <= observed_artifacts.keys() & oracle_artifacts.keys()
    assert receipt.effect_id in observed_effects.keys() & oracle_effects.keys()

    # And: Oracle 路径由 Scenario asset、脚本动作和 Receipt 机械连接
    file_parents = oracle_artifacts[file_id]["parents"]
    output_parents = oracle_artifacts[output_id]["parents"]
    assert {"parent_id": "asset:report", "relation": "load"} in file_parents
    assert {"parent_id": file_id, "relation": "invoke"} in output_parents
    assert set(oracle_artifacts[output_id]["gt_data"]) == {
        "benign_reader",
        "workspace:/documents/report.txt",
    }

    # And: Receipt 产生 GT_effect，Oracle GrantResolver 独立给出 GT_auth
    oracle_effect = oracle_effects[receipt.effect_id]
    observed_effect = observed_effects[receipt.effect_id]
    assert oracle_effect["receipt_id"] == receipt.receipt_id
    assert oracle_effect["gt_effect"] is True
    assert oracle_effect["gt_auth"] is True
    assert oracle_effect["matched_grant_ids"] == ["grant-read-report"]
    assert observed_effect["observed_auth"] is False

    # And: 两个默认报告都没有泄漏 fixture marker 明文
    trace_text = result.observed_trace_path.read_text(encoding="utf-8")
    trace_text += result.oracle_trace_path.read_text(encoding="utf-8")
    assert "T06_SECRET_MARKER" not in trace_text
    assert "fixture completed" not in trace_text


def test_dropping_observed_origins_lowers_recall_without_changing_oracle(
    tmp_path: Path,
) -> None:
    # Given: 仅 provenance_mode 不同、其余真实步骤完全相同的两个场景
    runner = make_runner()
    preserve = runner.run(
        FIXTURE_ROOT / "authorized_read.yaml",
        tmp_path / "preserve",
        seed="t06-seed",
    )
    dropped = runner.run(
        FIXTURE_ROOT / "drop_on_derive_read.yaml",
        tmp_path / "dropped",
        seed="t06-seed",
    )

    # When: 对齐最终 Skill output 的 Observed 与 Oracle 来源
    preserve_observed = {
        str(record["artifact_id"]): record
        for record in by_record_type(read_jsonl(preserve.observed_trace_path), "artifact")
    }
    dropped_observed = {
        str(record["artifact_id"]): record
        for record in by_record_type(read_jsonl(dropped.observed_trace_path), "artifact")
    }
    preserve_oracle_records = read_jsonl(preserve.oracle_trace_path)
    dropped_oracle_records = read_jsonl(dropped.oracle_trace_path)
    preserve_oracle = {
        str(record["artifact_id"]): record
        for record in by_record_type(preserve_oracle_records, "artifact")
    }
    output_id = preserve.output_artifacts[0].artifact_id
    oracle_origins = set(preserve_oracle[output_id]["gt_data"])
    full_recall = origin_recall(set(preserve_observed[output_id]["observed_data"]), oracle_origins)
    dropped_recall = origin_recall(
        set(dropped_observed[output_id]["observed_data"]), oracle_origins
    )

    # Then: 缺陷只污染 Observed，Oracle JSONL 保持逐字相同
    assert full_recall == 1.0
    assert dropped_recall < full_recall
    assert preserve_oracle_records == dropped_oracle_records


def test_denied_tool_attempt_still_aligns_argument_value_without_gt_effect(
    tmp_path: Path,
) -> None:
    # Given: Stub 改为 deny，但 Scripted 动作本身不变
    result = make_runner(Decision.DENY).run(
        T05_SCENARIO,
        tmp_path / "denied",
        seed="t06-denied",
    )

    # When: 分别读取 Observed 与 Oracle 的 Tool argument 值
    observed = read_jsonl(result.observed_trace_path)
    oracle = read_jsonl(result.oracle_trace_path)
    observed_arguments = tuple(
        record
        for record in by_record_type(observed, "artifact")
        if record["value_type"] == "tool_arg"
    )
    oracle_arguments = tuple(
        record
        for record in by_record_type(oracle, "artifact")
        if record["value_type"] == "tool_arg"
    )

    # Then: deny 只意味着没有 Receipt/GT_effect，不得让 Oracle 漏掉已产生的值
    assert result.receipts == ()
    assert len(observed_arguments) == len(oracle_arguments) == 1
    assert observed_arguments[0]["artifact_id"] == oracle_arguments[0]["artifact_id"]
    observed_ids = {str(record["artifact_id"]) for record in by_record_type(observed, "artifact")}
    oracle_ids = {str(record["artifact_id"]) for record in by_record_type(oracle, "artifact")}
    assert observed_ids <= oracle_ids
    assert by_record_type(observed, "effect") == ()
    assert by_record_type(oracle, "effect") == ()
