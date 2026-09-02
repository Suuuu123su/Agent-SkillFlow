from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from skillflow.experiment.t16.provider import TokenUsage
from skillflow.experiment.t17 import live_supervisor_cli as cli_module
from skillflow.experiment.t17.live_matrix import T17LiveStage
from skillflow.experiment.t17.live_stage_support import T17LiveProgressEvent
from skillflow.experiment.t17.live_supervisor_cli import (
    T17ConsoleProgress,
    _load_and_confirm_proposal,
    _print_stage_result,
    _require_new_campaign_root,
    run_live_supervisor_cli,
)


def test_live_supervisor_cli_stops_after_failed_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    campaign = tmp_path / "campaign"
    confirmed = object()
    summary = SimpleNamespace(
        live_gate_passed=False,
        stage=T17LiveStage.CANARY,
        completed_core_trials=0,
        scheduled_core_trials=24,
        completed_replay_pairs=0,
        scheduled_replay_pairs=18,
        telemetry=SimpleNamespace(
            api_call_count=0,
            token_usage=TokenUsage(
                input_tokens=0,
                cached_input_tokens=0,
                output_tokens=0,
                reasoning_tokens=0,
            ),
            estimated_cost_usd=0,
            conservative_reserved_usd=0,
        ),
    )
    stage_result = SimpleNamespace(
        result=SimpleNamespace(summary=summary),
        metrics=SimpleNamespace(required_metrics_complete=False),
        prepared=SimpleNamespace(attempt_root=tmp_path / "attempt"),
    )

    class FakeSupervisor:
        def __init__(self, *_args: object) -> None:
            self.results: tuple[object, ...] = ()

        def run_confirmed_stage(self, *_args: object) -> object:
            self.results = (stage_result,)
            return stage_result

    monkeypatch.setattr(cli_module, "_load_and_confirm_proposal", lambda *_args: confirmed)
    monkeypatch.setattr(cli_module, "read_t17_api_key", lambda: SecretStr("secret"))
    monkeypatch.setattr(cli_module, "T17LiveSupervisor", FakeSupervisor)
    monkeypatch.setattr(cli_module, "_print_stage_result", lambda _result: None)

    results = run_live_supervisor_cli(
        tmp_path,
        campaign,
        T17LiveStage.CANARY,
        tmp_path / "proposal.json",
    )

    assert results == (stage_result,)
    assert campaign.is_dir()


def test_live_supervisor_cli_helpers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:

    T17ConsoleProgress()(
        T17LiveProgressEvent(
            completed_units=1,
            scheduled_units=2,
            failed_units=0,
            api_call_count=3,
            total_tokens=4,
            estimated_cost_usd="0.1",
            conservative_reserved_usd="0.2",
        )
    )
    assert "complete=1/2" in capsys.readouterr().out
    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(Exception, match="Campaign"):
        _require_new_campaign_root(existing)
    _require_new_campaign_root(tmp_path / "new")

    proposal_path = Path("docs/evidence/t17-e-budget-proposal.json")
    monkeypatch.setattr(cli_module.typer, "confirm", lambda *_args, **_kwargs: True)
    confirmed = _load_and_confirm_proposal(T17LiveStage.CANARY, proposal_path)
    assert confirmed is not None
    with pytest.raises(Exception, match="不是 model1"):
        _load_and_confirm_proposal(T17LiveStage.MODEL1, proposal_path)

    summary = SimpleNamespace(
        stage=T17LiveStage.CANARY,
        live_gate_passed=True,
        completed_core_trials=24,
        scheduled_core_trials=24,
        completed_replay_pairs=18,
        scheduled_replay_pairs=18,
        telemetry=SimpleNamespace(
            api_call_count=1,
            token_usage=TokenUsage(
                input_tokens=1,
                cached_input_tokens=0,
                output_tokens=1,
                reasoning_tokens=1,
            ),
            estimated_cost_usd=0.1,
            conservative_reserved_usd=0.1,
        ),
    )
    result = SimpleNamespace(
        result=SimpleNamespace(summary=summary),
        metrics=SimpleNamespace(required_metrics_complete=True),
        prepared=SimpleNamespace(attempt_root=tmp_path),
    )
    _print_stage_result(result)
    assert "stage=canary" in capsys.readouterr().out


def test_live_supervisor_cli_builds_followup_then_honors_decline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    campaign = tmp_path / "campaign-followup"
    confirmed = object()
    prepared = SimpleNamespace(attempt_root=tmp_path / "canary-attempt")
    stage_result = SimpleNamespace(
        result=SimpleNamespace(summary=SimpleNamespace(live_gate_passed=True)),
        metrics=SimpleNamespace(required_metrics_complete=True),
        prepared=prepared,
    )

    class FakeSupervisor:
        def __init__(self, *_args: object) -> None:
            self.results: tuple[object, ...] = ()

        def run_confirmed_stage(self, *_args: object) -> object:
            self.results = (stage_result,)
            return stage_result

    confirmations = iter((confirmed, None))
    written: list[Path] = []
    monkeypatch.setattr(
        cli_module,
        "_load_and_confirm_proposal",
        lambda *_args: next(confirmations),
    )
    monkeypatch.setattr(cli_module, "read_t17_api_key", lambda: SecretStr("secret"))
    monkeypatch.setattr(cli_module, "T17LiveSupervisor", FakeSupervisor)
    monkeypatch.setattr(cli_module, "_print_stage_result", lambda _result: None)
    monkeypatch.setattr(cli_module, "load_live_matrix", lambda _path: object())
    monkeypatch.setattr(
        cli_module,
        "build_followup_budget_proposal",
        lambda *_args: object(),
    )
    monkeypatch.setattr(
        cli_module,
        "write_budget_proposal",
        lambda path, _proposal: written.append(path),
    )

    results = run_live_supervisor_cli(
        tmp_path,
        campaign,
        T17LiveStage.CANARY,
        tmp_path / "proposal.json",
    )

    assert results == (stage_result,)
    assert written == [campaign / "budget-proposals" / "model1.json"]


def test_live_supervisor_cli_stops_after_defense_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    campaign = tmp_path / "campaign-defense"
    stage_result = SimpleNamespace(
        result=SimpleNamespace(summary=SimpleNamespace(live_gate_passed=True)),
        metrics=SimpleNamespace(required_metrics_complete=True),
        prepared=SimpleNamespace(attempt_root=tmp_path / "defense-attempt"),
    )

    class FakeSupervisor:
        def __init__(self, *_args: object) -> None:
            self.results: tuple[object, ...] = ()

        def run_confirmed_stage(self, *_args: object) -> object:
            self.results = (stage_result,)
            return stage_result

    monkeypatch.setattr(
        cli_module,
        "_load_and_confirm_proposal",
        lambda *_args: object(),
    )
    monkeypatch.setattr(cli_module, "read_t17_api_key", lambda: SecretStr("secret"))
    monkeypatch.setattr(cli_module, "T17LiveSupervisor", FakeSupervisor)
    monkeypatch.setattr(cli_module, "_print_stage_result", lambda _result: None)

    results = run_live_supervisor_cli(
        tmp_path,
        campaign,
        T17LiveStage.DEFENSE,
        tmp_path / "proposal.json",
    )

    assert results == (stage_result,)
