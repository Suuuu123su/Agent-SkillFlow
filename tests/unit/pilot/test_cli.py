from pathlib import Path

import pytest
from typer.testing import CliRunner

from skillflow.pilot import cli
from skillflow.pilot.errors import PilotRunError
from skillflow.pilot.models import PilotReport


def test_cli_runs_the_pinned_pilot_and_reports_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[object] = []
    monkeypatch.setattr(cli, "_executable", Path)

    def execute(request: object) -> PilotReport:
        captured.append(request)
        return PilotReport(
            openclaw_commit="4" * 40,
            comparisons=(),
            real_credentials_used=False,
            external_effects_replaced=True,
            production_state_modified=False,
        )

    monkeypatch.setattr(cli, "execute_t15_pilot", execute)
    result = CliRunner().invoke(
        cli.app,
        [
            "--openclaw-root",
            str(tmp_path / "openclaw"),
            "--output",
            str(tmp_path / "output"),
            "--project-root",
            str(tmp_path / "project"),
        ],
    )

    assert result.exit_code == 0
    assert "[通过] T15 Pilot 场景=0" in result.output
    assert len(captured) == 1


def test_cli_turns_structured_pilot_failure_into_exit_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli, "_executable", Path)
    monkeypatch.setattr(
        cli,
        "execute_t15_pilot",
        lambda request: (_ for _ in ()).throw(PilotRunError.output_exists("evidence")),
    )

    result = CliRunner().invoke(
        cli.app,
        ["--openclaw-root", str(tmp_path / "openclaw"), "--output", str(tmp_path / "output")],
    )

    assert result.exit_code == 1
    assert "[失败] Pilot 输出目录已存在" in result.output
