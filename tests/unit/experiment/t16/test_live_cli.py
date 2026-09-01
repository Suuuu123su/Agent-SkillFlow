from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import SecretStr

from skillflow.experiment.t16.live_cli import (
    EmptyApiKeyError,
    LiveCampaignResult,
    SupervisedCampaignRequest,
    read_api_key,
    run_supervised_campaign,
)
from skillflow.experiment.t16.live_run_models import LivePhaseSummary

ROOT = Path(__file__).parents[4]


def test_api_key_is_read_from_hidden_prompt_only_and_wrapped_as_secret() -> None:
    prompts: list[str] = []

    def reader(prompt: str) -> str:
        prompts.append(prompt)
        return "temporary-test-secret"

    secret = read_api_key(reader)

    assert isinstance(secret, SecretStr)
    assert str(secret) == "**********"
    assert prompts == ["请输入新的 OpenAI API Key（输入不可见）："]


def test_empty_api_key_is_rejected_without_environment_fallback() -> None:
    with pytest.raises(EmptyApiKeyError):
        read_api_key(lambda _prompt: "")

    source = (ROOT / "src" / "skillflow" / "experiment" / "t16" / "live_cli.py").read_text(
        encoding="utf-8"
    )
    assert "OPENAI_API_KEY" not in source
    assert "os.environ" not in source
    assert "dotenv" not in source


def _summary(
    *,
    stop_detail: str | None,
    reserved: Decimal,
    gate: bool,
) -> LivePhaseSummary:
    return LivePhaseSummary.model_construct(
        stop_detail=stop_detail,
        conservative_reserved_usd=reserved,
        live_gate_passed=gate,
    )


@dataclass
class ScriptedAttemptRunner:
    results: list[LiveCampaignResult]
    calls: list[tuple[Path, SecretStr, Decimal]] = field(default_factory=list)

    def __call__(
        self,
        attempt_root: Path,
        api_key: SecretStr,
        initial_total_reserved_usd: Decimal,
    ) -> LiveCampaignResult:
        self.calls.append((attempt_root, api_key, initial_total_reserved_usd))
        return self.results.pop(0)


def test_supervisor_reuses_one_in_memory_secret_across_bounded_smoke_recovery(
    tmp_path: Path,
) -> None:
    secret = SecretStr("one-prompt-only")
    failed = LiveCampaignResult(
        smoke=_summary(
            stop_detail="timeout",
            reserved=Decimal("0.10"),
            gate=False,
        ),
        model1=None,
        metrics=None,
    )
    succeeded = LiveCampaignResult(
        smoke=_summary(stop_detail=None, reserved=Decimal("0.20"), gate=True),
        model1=_summary(stop_detail=None, reserved=Decimal("0.40"), gate=True),
        metrics=None,
    )
    runner = ScriptedAttemptRunner([failed, succeeded])

    result = run_supervised_campaign(
        SupervisedCampaignRequest(ROOT, tmp_path),
        secret,
        attempt_runner=runner,
        sleep=lambda _seconds: None,
    )

    assert result.final is succeeded
    assert [call[0].name for call in runner.calls] == ["attempt-01", "attempt-02"]
    assert all(call[1] is secret for call in runner.calls)
    assert [call[2] for call in runner.calls] == [Decimal(0), Decimal("0.10")]
