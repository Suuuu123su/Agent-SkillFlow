from pathlib import Path
from typing import cast

import pytest
from pydantic import SecretStr

from skillflow.experiment.io import write_json_model
from skillflow.experiment.t17.budget_proposal import T17BudgetProposal
from skillflow.experiment.t17.live_matrix import T17LiveStage
from skillflow.experiment.t17.live_stage import T17LiveStageResult
from skillflow.experiment.t17.live_stage_support import T17LiveProgressSink
from skillflow.experiment.t17.live_supervisor import (
    T17EmptyApiKeyError,
    T17LiveSupervisor,
    T17PreparedLiveStage,
    load_and_confirm_budget_proposal,
    read_t17_api_key,
)
from skillflow.experiment.t17.metric_models import T17PhaseMetricsReport

CANARY_PROPOSAL = Path("docs/evidence/t17-e-budget-proposal.json")


def test_read_t17_api_key_reads_hidden_secret_once() -> None:
    prompts: list[str] = []

    def read_once(prompt: str) -> str:
        prompts.append(prompt)
        return "unit-test-secret"

    secret = read_t17_api_key(read_once)

    assert isinstance(secret, SecretStr)
    assert secret.get_secret_value() == "unit-test-secret"
    assert len(prompts) == 1


def test_read_t17_api_key_rejects_empty_input() -> None:
    with pytest.raises(T17EmptyApiKeyError):
        read_t17_api_key(lambda _prompt: "")


def test_supervisor_reuses_same_secret_across_approved_stages(
    tmp_path: Path,
) -> None:
    # Given: two zero-call proposals and a fake executor.
    canary = T17BudgetProposal.model_validate_json(CANARY_PROPOSAL.read_text(encoding="utf-8"))
    model1 = canary.model_copy(
        update={
            "stage": T17LiveStage.MODEL1,
            "scheduled_core_trials": 360,
            "scheduled_replay_pairs": 270,
        }
    )
    model1_path = tmp_path / "model1-budget-proposal.json"
    write_json_model(model1_path, model1)
    observed_secrets: list[SecretStr] = []

    def fake_executor(
        _prepared: T17PreparedLiveStage,
        secret: SecretStr,
        _progress: T17LiveProgressSink | None,
    ) -> T17LiveStageResult:
        observed_secrets.append(secret)
        return cast("T17LiveStageResult", object())

    def fake_reporter(
        _prepared: T17PreparedLiveStage,
        _result: T17LiveStageResult,
    ) -> T17PhaseMetricsReport:
        return cast("T17PhaseMetricsReport", object())

    secret = SecretStr("one-process-secret")
    supervisor = T17LiveSupervisor(
        Path(),
        tmp_path / "campaign",
        secret,
        fake_executor,
        fake_reporter,
    )
    confirmed_canary = load_and_confirm_budget_proposal(
        CANARY_PROPOSAL,
        lambda _proposal: True,
    )
    confirmed_model1 = load_and_confirm_budget_proposal(
        model1_path,
        lambda _proposal: True,
    )
    assert confirmed_canary is not None
    assert confirmed_model1 is not None

    # When: Canary and Model1 are prepared and dispatched in one process.
    supervisor.run_confirmed_stage(confirmed_canary)
    supervisor.run_confirmed_stage(confirmed_model1)

    # Then: both stages receive the identical in-memory SecretStr object.
    assert observed_secrets == [secret, secret]


def test_confirmed_proposal_bytes_survive_source_path_replacement(
    tmp_path: Path,
) -> None:
    # Given: a proposal confirmed from a temporary source path.
    source = tmp_path / "proposal.json"
    source.write_bytes(CANARY_PROPOSAL.read_bytes())
    confirmed = load_and_confirm_budget_proposal(
        source,
        lambda _proposal: True,
    )
    assert confirmed is not None
    original = confirmed.raw_bytes
    source.write_text('{"replaced":true}\n', encoding="utf-8")
    captured: list[T17PreparedLiveStage] = []

    def fake_executor(
        prepared: T17PreparedLiveStage,
        _secret: SecretStr,
        _progress: T17LiveProgressSink | None,
    ) -> T17LiveStageResult:
        captured.append(prepared)
        return cast("T17LiveStageResult", object())

    def fake_reporter(
        _prepared: T17PreparedLiveStage,
        _result: T17LiveStageResult,
    ) -> T17PhaseMetricsReport:
        return cast("T17PhaseMetricsReport", object())

    supervisor = T17LiveSupervisor(
        Path(),
        tmp_path / "campaign-toctou",
        SecretStr("secret"),
        fake_executor,
        fake_reporter,
    )

    # When: the confirmed capability is executed after source replacement.
    supervisor.run_confirmed_stage(confirmed)

    # Then: Attempt and approval use the originally confirmed exact bytes.
    assert captured[0].proposal_path.read_bytes() == original
    assert captured[0].proposal == confirmed.proposal
