import json
from pathlib import Path

from jsonschema import Draft202012Validator
from typer.testing import CliRunner

from skillflow.cli import app

runner = CliRunner()
SCENARIO = Path("scenarios/benign/b0_legal_summary.yaml")


def test_run_builds_a_complete_single_run_experiment(tmp_path: Path) -> None:
    # Given: 一个可离线执行的良性 Scenario 与全新输出目录
    output = tmp_path / "single"

    # When: 通过公开 CLI 建立 single-run Experiment
    result = runner.invoke(
        app,
        ["run", str(SCENARIO), "--mode", "monitor", "--output", str(output)],
    )

    # Then: 顶层事实、聚合和逐 Run 派生产物一次生成完毕
    assert result.exit_code == 0, result.output
    for name in (
        "experiment-manifest.json",
        "aggregate-metrics.json",
        "summary.csv",
        "experiment-report.json",
        "state.sqlite",
    ):
        assert (output / name).is_file()
    assert (output / "blobs").is_dir()

    experiment_manifest = json.loads(
        (output / "experiment-manifest.json").read_text(encoding="utf-8")
    )
    assert experiment_manifest["experiment_id"] == "single"
    assert experiment_manifest["backend"] == "scripted"
    assert experiment_manifest["redacted"] is True
    assert len(experiment_manifest["run_ids"]) == 1
    run_id = experiment_manifest["run_ids"][0]

    run_root = output / "runs" / run_id
    for name in (
        "run-manifest.json",
        "observed-trace.jsonl",
        "oracle-trace.jsonl",
        "graph.json",
        "run-report.json",
    ):
        assert (run_root / name).is_file()

    report = json.loads((run_root / "run-report.json").read_text(encoding="utf-8"))
    assert report["report_scope"] == "run"
    assert report["experiment_id"] == "single"
    assert report["scenario"] == SCENARIO.as_posix()
    assert report["variant"] == "single"
    assert report["seed"] == 0
    assert report["backend"] == "scripted"
    assert report["task_success"] is True
    assert report["latency_ms"] == 0.0
    assert len(report["effect_ids"]) == len(report["authorized_flags"])
    assert len(report["effect_ids"]) == len(report["baseline_decisions"])
    assert len(report["effect_ids"]) == len(report["policy_decisions"])
    assert "source_to_sink_paths" in report

    schema = json.loads(Path("schemas/risk-report.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(report)
    exported = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            output / "experiment-manifest.json",
            output / "aggregate-metrics.json",
            output / "summary.csv",
            output / "experiment-report.json",
            run_root / "run-manifest.json",
            run_root / "observed-trace.jsonl",
            run_root / "oracle-trace.jsonl",
            run_root / "graph.json",
            run_root / "run-report.json",
        )
    )
    assert "summary: report accepted" not in exported
    assert str(tmp_path) not in exported
