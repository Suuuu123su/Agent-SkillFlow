import csv
import json
from pathlib import Path

from typer.testing import CliRunner

from skillflow.cli import app


def test_mvp_matrix_builds_runs_replays_and_aggregate_report(tmp_path: Path) -> None:
    output = tmp_path / "mvp"

    result = CliRunner().invoke(
        app,
        [
            "matrix",
            "scenarios/matrix/mvp.yaml",
            "--backend",
            "scripted",
            "--output",
            str(output),
            "--determinism-repeats",
            "1",
        ],
    )

    assert result.exit_code == 0, result.output
    manifest = _json(output / "experiment-manifest.json")
    report = _json(output / "experiment-report.json")
    run_ids = manifest["run_ids"]
    replay_ids = manifest["replay_ids"]
    assert manifest["kind"] == "matrix"
    assert manifest["determinism_repeats"] == 1
    assert len(run_ids) == 24
    assert len(manifest["determinism_checks"]) == 24
    assert all(check["consistent"] is True for check in manifest["determinism_checks"])
    assert len(replay_ids) == 18

    for run_id in run_ids:
        run_root = output / "runs" / run_id
        assert {path.name for path in run_root.iterdir()} == {
            "run-manifest.json",
            "observed-trace.jsonl",
            "oracle-trace.jsonl",
            "graph.json",
            "run-report.json",
        }
    for replay_id in replay_ids:
        replay_root = output / "replays" / replay_id
        assert {path.name for path in replay_root.iterdir()} == {
            "pair-manifest.json",
            "replay-report.json",
        }

    assert len(report["hiaa_designs"]) == 2
    assert {item["HIAA_run"]["value"] for item in report["hiaa_designs"]} == {1.0}
    assert report["ALR"]["numerator"] == 1
    assert report["ALR"]["denominator"] >= 1
    assert report["RIR_1"]["numerator"] >= 1
    assert report["RIR_1"]["denominator"] >= report["RIR_1"]["numerator"]
    assert report["RIR_3"]["numerator"] >= 1
    assert report["RIR_3"]["denominator"] >= report["RIR_3"]["numerator"]

    with (output / "summary.csv").open(encoding="utf-8", newline="") as stream:
        rows = tuple(csv.DictReader(stream))
    assert len(rows) == 24
    assert {row["run_id"] for row in rows} == set(run_ids)
    assert (output / "state.sqlite").is_file()


def _json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload
