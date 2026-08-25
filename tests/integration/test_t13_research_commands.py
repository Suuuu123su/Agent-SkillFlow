import json
from pathlib import Path

from typer.testing import CliRunner

from skillflow.cli import app


def test_run_analysis_replay_aggregate_and_export_commands(tmp_path: Path) -> None:
    experiment = tmp_path / "a1-study"
    runner = CliRunner()
    started = runner.invoke(
        app,
        [
            "run",
            "scenarios/attacks/a1_implicit_text_authorization.yaml",
            "--output",
            str(experiment),
        ],
    )
    assert started.exit_code == 0, started.output
    manifest = _json(experiment / "experiment-manifest.json")
    run_id = str(manifest["run_ids"][0])
    run_report = _json(experiment / "runs" / run_id / "run-report.json")
    artifact_id = str(run_report["counterfactual_artifacts"][0]["artifact_id"])

    analyzed = runner.invoke(app, ["analyze", run_id, "--runs-root", str(tmp_path)])
    assert analyzed.exit_code == 0, analyzed.output
    graphed = runner.invoke(app, ["graph", run_id, "--runs-root", str(tmp_path)])
    assert graphed.exit_code == 0, graphed.output
    assert f'"run_id":"{run_id}"' in graphed.output.replace(" ", "")
    replayed = runner.invoke(
        app,
        [
            "replay",
            run_id,
            "--neutralize-artifact",
            artifact_id,
            "--runs-root",
            str(tmp_path),
        ],
    )
    assert replayed.exit_code == 0, replayed.output
    replay_reports = tuple((experiment / "replays").glob("*/replay-report.json"))
    assert len(replay_reports) == 1

    aggregated = runner.invoke(
        app,
        ["aggregate", "a1-study", "--runs-root", str(tmp_path)],
    )
    assert aggregated.exit_code == 0, aggregated.output
    report = _json(experiment / "experiment-report.json")
    assert report["ALR"]["numerator"] == 1
    assert report["ALR"]["denominator"] == 1

    run_export = tmp_path / "run-export.json"
    experiment_export = tmp_path / "experiment-export.json"
    for scope, identifier, output in (
        ("run", run_id, run_export),
        ("experiment", "a1-study", experiment_export),
    ):
        exported = runner.invoke(
            app,
            [
                "export",
                "--scope",
                scope,
                identifier,
                "--output",
                str(output),
                "--runs-root",
                str(tmp_path),
            ],
        )
        assert exported.exit_code == 0, exported.output
        assert _json(output)["report_scope"] == scope


def test_factorial_builds_two_levels_for_each_seed(tmp_path: Path) -> None:
    output = tmp_path / "factorial"
    result = CliRunner().invoke(
        app,
        [
            "factorial",
            "scenarios/benign/b0_legal_summary.yaml",
            "--feature",
            "persistent_memory",
            "--seeds",
            "0",
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0, result.output
    manifest = _json(output / "experiment-manifest.json")
    assert manifest["kind"] == "factorial"
    assert len(manifest["run_ids"]) == 2


def _json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload
