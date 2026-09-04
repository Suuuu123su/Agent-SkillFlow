import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skillflow.cli import app
from skillflow.experiment.t18 import cli
from skillflow.experiment.t18.dataset import load_dataset
from tests.unit.defense.test_contracts import signal

ROOT = Path(__file__).resolve().parents[3]
RUNNER = CliRunner()


def test_catalog_lists_only_fixed_scope() -> None:
    result = RUNNER.invoke(app, ["defense", "catalog", "--root", str(ROOT)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert len(payload["skills"]) == 28
    assert payload["scripted_core"] == 264
    assert payload["fake_core"] == 44


def test_diagnose_uses_closed_signals(tmp_path: Path) -> None:
    path = tmp_path / "signal.json"
    path.write_text(signal(grant_missing=True).model_dump_json(), encoding="utf-8")
    result = RUNNER.invoke(app, ["defense", "diagnose", "--signals", str(path)])
    assert result.exit_code == 0, result.output
    value = json.loads(result.output)
    assert value["diagnosis"]["mechanisms"] == ["privilege"]
    assert "task-alignment" in value["plan"]["selected_defense_ids"]
    forbidden = signal().model_dump(mode="json")
    forbidden["attack_family"] = "privilege"
    path.write_text(json.dumps(forbidden), encoding="utf-8")
    assert RUNNER.invoke(app, ["defense", "diagnose", "--signals", str(path)]).exit_code == 2


@pytest.mark.parametrize("domain", ["scripted", "fake_reference"])
def test_matrix_cli_dispatches_only_explicit_batch(
    domain: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []

    def batch(root: Path, output: Path, selected: str, maximum: int) -> dict[str, int]:
        calls.append((root, output, selected, maximum))
        return {"new_core": 0, "completed": 44}

    monkeypatch.setattr(cli, "run_batch", batch)
    arguments = [
        "defense",
        "run-matrix",
        "--root",
        str(ROOT),
        "--output",
        str(tmp_path / "t18-cli"),
        "--domain",
        domain,
        "--maximum-cores",
        "1",
    ]
    result = RUNNER.invoke(app, arguments)
    assert result.exit_code == 0, result.output
    assert calls == [(ROOT, tmp_path / "t18-cli", domain, 1)]


@pytest.mark.parametrize(
    "arguments",
    [
        ["catalog", "--root", "missing-t18-root"],
        ["diagnose", "--signals", "missing-signal.json"],
        ["run-matrix", "--root", ".", "--output", "t18-unused", "--domain", "live"],
        [
            "run-matrix",
            "--root",
            ".",
            "--output",
            "t18-unused",
            "--domain",
            "scripted",
            "--maximum-cores",
            "49",
        ],
        ["report", "--output", "unused"],
        ["report", "--output", "unused", "--run", "missing"],
        ["report", "--output", "unused", "--dataset", "missing"],
    ],
)
def test_cli_rejects_missing_invalid_or_unapproved_modes(arguments: list[str]) -> None:
    assert RUNNER.invoke(app, ["defense", *arguments]).exit_code == 2


def test_cli_report_export_and_recompute(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = load_dataset(ROOT / "datasets/t18-local/fake_reference", verify=False)
    monkeypatch.setattr(cli, "load_run", lambda *_: data)
    export = RUNNER.invoke(
        app,
        [
            "defense",
            "report",
            "--root",
            str(ROOT),
            "--run",
            "existing-validated-run",
            "--output",
            str(tmp_path / "public"),
        ],
    )
    assert export.exit_code == 0, export.output
    result = RUNNER.invoke(
        app,
        [
            "defense",
            "report",
            "--dataset",
            str(tmp_path / "public"),
            "--output",
            str(tmp_path / "recomputed"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["compared_files"] == 3
