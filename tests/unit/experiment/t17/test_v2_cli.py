"""完整第二版命令必须可发现，且冻结不发请求、不覆盖文件。"""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from skillflow.cli import app
from skillflow.experiment.t17.live_matrix import T17LiveStage
from skillflow.experiment.t17.v2.config_models import V2Matrix


@pytest.mark.parametrize("args", [["t17", "v2", "--help"], ["compare-skills", "--help"]])
def test_v2_commands_are_registered(args: list[str]) -> None:
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output


def test_v2_cli_freeze_has_five_exact_stages_and_no_overwrite(t17_cli_root: Path) -> None:
    output = t17_cli_root / "cli-v2-freeze"
    args = ["t17", "v2", "freeze", "--output", str(output)]
    runner = CliRunner()
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert "API=0" in result.output
    expected = [(24, 18), (360, 270), (24, 18), (360, 270), (270, 270)]
    for stage, counts in zip(T17LiveStage, expected, strict=True):
        matrix = V2Matrix.model_validate_json(
            (output / f"matrix-{stage.value}.json").read_text(encoding="utf-8")
        )
        assert (matrix.scheduled_core_trials, matrix.scheduled_replay_pairs) == counts
    assert runner.invoke(app, args).exit_code == 2


def test_v2_cli_rejects_project_escape() -> None:
    output = Path.cwd().parent / "forbidden-v2-output"
    result = CliRunner().invoke(app, ["t17", "v2", "freeze", "--output", str(output)])
    assert result.exit_code == 2
    assert not output.exists()
