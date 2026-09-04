"""命令入口的成功、拒绝及错误脱敏；底层实验一律使用本地替身。"""

from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import typer
from pydantic import SecretStr
from typer.testing import CliRunner

from skillflow.experiment.t17.live_matrix import T17LiveStage
from skillflow.experiment.t17.v2 import campaign_cli, cli
from skillflow.experiment.t17.v2.campaign_models import StageProgress
from skillflow.experiment.t17.v2.fake_client import V2FakeClient
from skillflow.experiment.t17.v2.run_models import UnitUsage


def test_schemas_create_only_inside_project(
    t17_cli_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    writer = Mock()
    monkeypatch.setattr(cli, "write_v2_schemas", writer)
    output = t17_cli_root / "schema-output"
    runner = CliRunner()
    result = runner.invoke(cli.v2_app, ["schemas", "--output", str(output)])
    assert result.exit_code == 0
    assert "API=0" in result.output
    writer.assert_called_once_with(output)
    for forbidden in (Path.cwd(), Path.cwd().parent):
        result = runner.invoke(cli.v2_app, ["schemas", "--output", str(forbidden)])
        assert result.exit_code == 2
    assert writer.call_count == 1


@pytest.mark.parametrize("fake", [False, True])
@pytest.mark.parametrize("passed", [False, True])
def test_offline_entrypoint_keeps_domain_and_failed_gate(
    t17_cli_root: Path,
    fake: bool,
    passed: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configuration, matrix = object(), object()
    monkeypatch.setattr(cli, "read_model", Mock(return_value=configuration))
    monkeypatch.setattr(cli, "build_matrix", Mock(return_value=matrix))
    execute = Mock(
        return_value=SimpleNamespace(
            cores=(1, 2), replays=(1,), gate=SimpleNamespace(passed=passed)
        )
    )
    monkeypatch.setattr(cli, "run_stage", execute)
    args = (t17_cli_root / "configuration.json", t17_cli_root / "offline")
    invoke = cli.fake_command if fake else cli.scripted_command
    if passed:
        invoke(*args)
    else:
        with pytest.raises(typer.Exit) as caught:
            invoke(*args)
        assert caught.value.exit_code == 2
    setup = execute.call_args.args[0]
    assert setup.configuration is configuration
    assert setup.matrix is matrix
    assert setup.domain == ("fake_reference" if fake else "scripted")
    assert isinstance(setup.client, V2FakeClient) if fake else setup.client is None


def test_offline_error_never_prints_exception_body(
    t17_cli_root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "read_model", Mock(side_effect=ValueError("private-prompt-body")))
    with pytest.raises(typer.Exit):
        cli.scripted_command(t17_cli_root / "input", t17_cli_root / "output")
    assert "private-prompt-body" not in capsys.readouterr().err


@pytest.mark.parametrize("input_kind", ["dataset", "attempt"])
@pytest.mark.parametrize("passed", [False, True])
def test_report_selects_exact_input_and_keeps_incomplete_status(
    t17_cli_root: Path,
    input_kind: str,
    passed: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded = object()
    dataset_loader = Mock(return_value=(loaded,))
    attempt_loader = Mock(return_value=loaded)
    exporter = Mock(
        return_value=SimpleNamespace(
            scheduled_core=24, scheduled_replay=18, all_provided_stages_passed=passed
        )
    )
    monkeypatch.setattr(cli, "load_dataset", dataset_loader)
    monkeypatch.setattr(cli, "load_stage", attempt_loader)
    monkeypatch.setattr(cli, "export_dataset", exporter)
    dataset = t17_cli_root if input_kind == "dataset" else None
    attempt = [t17_cli_root] if input_kind == "attempt" else None
    if passed:
        cli.report_command(t17_cli_root / "output", dataset, attempt)
    else:
        with pytest.raises(typer.Exit):
            cli.report_command(t17_cli_root / "output", dataset, attempt)
    assert exporter.call_args.args[2] == (loaded,)
    assert dataset_loader.call_count == (input_kind == "dataset")
    assert attempt_loader.call_count == (input_kind == "attempt")


@pytest.mark.parametrize("both", [False, True])
def test_report_refuses_missing_or_ambiguous_input(
    t17_cli_root: Path, both: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    loader = Mock()
    monkeypatch.setattr(cli, "load_dataset", loader)
    with pytest.raises(typer.Exit):
        cli.report_command(
            t17_cli_root / "output",
            t17_cli_root if both else None,
            [t17_cli_root] if both else None,
        )
    loader.assert_not_called()


@pytest.mark.parametrize("status", ["passed", "failed", "error"])
def test_golden_entrypoint_reports_failure_without_relabeling_success(
    t17_cli_root: Path,
    status: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = Mock(
        return_value=SimpleNamespace(core=24, replay=18, replicas=5, passed=status == "passed")
    )
    if status == "error":
        run.side_effect = OSError("private-golden-body")
    monkeypatch.setattr(cli, "run_golden", run)
    result = CliRunner().invoke(
        cli.v2_app,
        ["golden", "--protocol", str(t17_cli_root), "--output", str(t17_cli_root / "golden")],
    )
    assert result.exit_code == (0 if status == "passed" else 2)
    assert "private-golden-body" not in result.output


def test_skill_comparison_errors_are_redacted(
    t17_cli_root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "load_dataset", Mock(side_effect=OSError("private-dataset-body")))
    with pytest.raises(typer.Exit):
        cli.compare_skills_command(t17_cli_root, t17_cli_root / "skills")
    assert "private-dataset-body" not in capsys.readouterr().err


@pytest.mark.parametrize("failed", [False, True])
def test_cost_plan_remains_proposal_not_live_authorization(
    t17_cli_root: Path,
    failed: bool,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    build = Mock(return_value=SimpleNamespace(requested_max_total_usd=Decimal("58.25")))
    if failed:
        build.side_effect = OSError("private-history-body")
    monkeypatch.setattr(campaign_cli, "write_cost_plan", build)
    if failed:
        with pytest.raises(typer.Exit):
            campaign_cli.cost_plan_command(t17_cli_root, t17_cli_root, t17_cli_root / "proposal")
    else:
        campaign_cli.cost_plan_command(t17_cli_root, t17_cli_root, t17_cli_root / "proposal")
    output = capsys.readouterr()
    assert "private-history-body" not in output.err
    if not failed:
        assert "58.25" in output.out
        assert "未授予调用权限" in output.out


@pytest.mark.parametrize("state", ["passed", "incomplete", "stopped", "error"])
def test_live_entrypoint_reads_key_once_only_after_preparation(
    t17_cli_root: Path,
    state: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    preparation = Mock(return_value=object())
    if state == "error":
        preparation.side_effect = ValueError("private-approval-body")
    key = Mock(return_value=SecretStr("synthetic-never-persisted"))
    result = (
        None
        if state == "stopped"
        else SimpleNamespace(
            stages=(1,),
            all_stages_finished=state == "passed",
            estimated_cost_usd=Decimal(0),
            reserved_cost_usd=Decimal(0),
        )
    )
    runner = Mock(return_value=result)
    monkeypatch.setattr(campaign_cli, "prepare_campaign", preparation)
    monkeypatch.setattr(
        campaign_cli, "create_session_control", Mock(return_value=t17_cli_root / "control")
    )
    monkeypatch.setattr(campaign_cli, "read_campaign_key", key)
    monkeypatch.setattr(campaign_cli, "run_key_session", runner)
    args = (t17_cli_root, t17_cli_root / "plan", t17_cli_root / "approval", t17_cli_root / "output")
    if state == "passed":
        campaign_cli.live_command(*args)
    else:
        with pytest.raises(typer.Exit) as caught:
            campaign_cli.live_command(*args)
        assert caught.value.exit_code == 2
    assert key.call_count == (state != "error")
    assert runner.call_count == (state != "error")
    output = capsys.readouterr()
    assert "synthetic-never-persisted" not in output.out + output.err
    assert "private-approval-body" not in output.out + output.err


def capture_live_callbacks(
    directory: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Callable[[StageProgress], None], Callable[[str], None]]:
    monkeypatch.setattr(campaign_cli, "prepare_campaign", Mock(return_value=object()))
    monkeypatch.setattr(campaign_cli, "create_session_control", Mock(return_value=directory))
    monkeypatch.setattr(
        campaign_cli, "read_campaign_key", Mock(return_value=SecretStr("local-test"))
    )
    result = SimpleNamespace(
        stages=(),
        all_stages_finished=True,
        estimated_cost_usd=0,
        reserved_cost_usd=0,
    )
    runner = Mock(return_value=result)
    monkeypatch.setattr(campaign_cli, "run_key_session", runner)
    campaign_cli.live_command(
        directory, directory / "plan", directory / "approval", directory / "output"
    )
    return runner.call_args.args[2], runner.call_args.args[3]


def test_progress_exposes_only_counts_and_costs(
    t17_cli_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    progress, _ = capture_live_callbacks(t17_cli_root, monkeypatch)
    capsys.readouterr()
    progress(
        StageProgress(
            stage=T17LiveStage.CANARY,
            scheduled_core=24,
            scheduled_replay=18,
            terminal_core=2,
            terminal_replay=1,
            failed_units=0,
            model_failures=1,
            usage=UnitUsage(api_calls=3, input_tokens=10, output_tokens=2, reasoning_tokens=1),
        )
    )
    output = capsys.readouterr().out
    assert "任务=2/24" in output
    assert "请求=3" in output
    assert "10/2/1" in output


@pytest.mark.parametrize("error", [OSError, UnicodeError, ValueError])
def test_display_failure_does_not_stop_key_keeper(
    t17_cli_root: Path,
    error: type[Exception],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, notice = capture_live_callbacks(t17_cli_root, monkeypatch)
    echo = Mock(side_effect=error("display unavailable"))
    monkeypatch.setattr(campaign_cli.typer, "echo", echo)
    notice("safe-counts")
    echo.assert_called_once_with("safe-counts")
