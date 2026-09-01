from contextlib import nullcontext
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
import typer
from pydantic import SecretStr

from skillflow.experiment.t16 import task_success_live_cli as cli
from skillflow.experiment.t16.provider import TokenUsage
from skillflow.experiment.t16.task_success_live_mock import TaskSuccessMockLiveClient
from skillflow.experiment.t16.task_success_live_models import (
    T16D2RunSummary,
    T16D2StopReason,
)

ROOT = Path(__file__).parents[4]


def _configure_live_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKILLFLOW_PROVIDER", "openai")
    monkeypatch.setenv("SKILLFLOW_MODEL_ID", "gpt-5.6-luna")
    monkeypatch.setenv("SKILLFLOW_MAX_USD", "3")
    monkeypatch.setenv("SKILLFLOW_LIVE_APPROVED", "1")


def _zero_usage() -> TokenUsage:
    return TokenUsage(
        input_tokens=0,
        cached_input_tokens=0,
        output_tokens=0,
        reasoning_tokens=0,
        cache_write_tokens=0,
    )


def _blocked_summary() -> T16D2RunSummary:
    return T16D2RunSummary(
        created_at=datetime.now(UTC),
        observed=11,
        unrun=37,
        canary_observed=11,
        canary_gate_passed=False,
        final_gate_passed=False,
        stop_reason=T16D2StopReason.CANARY_GATE_BLOCKED,
        stop_detail="technical_gate_blocked",
        infrastructure_invalid=0,
        conservative_reserved_usd=Decimal(0),
        actual_estimated_cost_usd=Decimal(0),
        token_usage=_zero_usage(),
        api_call_count=0,
        raw_records_sha256="0" * 64,
    )


def test_cli_reads_one_hidden_key_and_runs_all_48_trials_with_mock_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _configure_live_environment(monkeypatch)
    key_reads = 0

    def read_once() -> SecretStr:
        nonlocal key_reads
        key_reads += 1
        return SecretStr("unit-test-only-secret")

    monkeypatch.setattr(cli, "read_api_key", read_once)
    monkeypatch.setattr(cli, "managed_httpx2_transport", lambda: nullcontext(object()))
    monkeypatch.setattr(
        cli,
        "OpenAIResponsesClient",
        lambda _secret, _transport: TaskSuccessMockLiveClient(),
    )
    output = tmp_path / "attempt-01"

    cli.main(ROOT, output)

    console = capsys.readouterr().out
    assert key_reads == 1
    assert "unit-test-only-secret" not in console
    assert "observed=48/48" in console
    assert (output / "stage-gate-final.json").is_file()


def test_cli_rejects_nonempty_attempt_before_reading_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_live_environment(monkeypatch)
    output = tmp_path / "existing-attempt"
    output.mkdir()
    (output / "existing.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        cli,
        "read_api_key",
        lambda: pytest.fail("非空 Attempt 不得读取密钥"),
    )

    with pytest.raises(typer.BadParameter, match="output_root"):
        cli.main(ROOT, output)


def test_cli_exits_nonzero_when_final_stage_gate_is_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_live_environment(monkeypatch)
    monkeypatch.setattr(cli, "read_api_key", lambda: SecretStr("unit-test-only-secret"))
    monkeypatch.setattr(cli, "managed_httpx2_transport", lambda: nullcontext(object()))
    monkeypatch.setattr(cli, "OpenAIResponsesClient", lambda _secret, _transport: object())
    monkeypatch.setattr(cli, "execute_t16d2_run", lambda *_args: _blocked_summary())

    with pytest.raises(typer.Exit) as caught:
        cli.main(ROOT, tmp_path / "blocked-attempt")

    assert caught.value.exit_code == 2
