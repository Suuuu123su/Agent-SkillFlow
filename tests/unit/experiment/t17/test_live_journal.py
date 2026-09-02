from decimal import Decimal
from pathlib import Path

import pytest

from skillflow.experiment.t16.budget import (
    BudgetLedger,
    CallReservation,
)
from skillflow.experiment.t16.live_agent_calls import ActualResponseUsage
from skillflow.experiment.t16.provider import TokenUsage
from skillflow.experiment.t17.live_attempt_models import (
    T17LiveTerminalStatus,
    T17LiveUnitKind,
)
from skillflow.experiment.t17.live_journal import (
    T17LiveUsageJournal,
    load_live_journal,
)
from skillflow.experiment.t17.live_journal_models import (
    T17LiveJournalBinding,
    T17LiveJournalError,
    T17LiveJournalErrorCode,
    T17ModelRevisionDriftError,
)
from skillflow.experiment.t17.live_matrix import (
    T17LiveStage,
    load_live_preregistration,
)
from skillflow.experiment.t17.live_reference_client import ReferenceLiveTelemetry


def _binding() -> T17LiveJournalBinding:
    return T17LiveJournalBinding(
        phase_contract_sha256="a" * 64,
        approved_config_sha256="b" * 64,
        stage=T17LiveStage.CANARY,
        model_id="gpt-5.6-luna",
        model_revision="gpt-5.6-luna",
    )


def _budget() -> BudgetLedger:
    registration = load_live_preregistration(Path("experiments/t17/preregistration.yaml"))
    config = registration.model1_budget.model_copy(update={"allow_live": True})
    return (
        BudgetLedger(config)
        .begin_run()
        .authorize_call(
            CallReservation(
                estimated_cost_usd=Decimal("0.01"),
                max_output_tokens=10,
            )
        )
    )


def _usage() -> TokenUsage:
    return TokenUsage(
        input_tokens=10,
        cached_input_tokens=0,
        output_tokens=2,
        reasoning_tokens=1,
    )


def test_live_usage_journal_hash_chain_and_secret_exclusion(
    tmp_path: Path,
) -> None:
    # Given: a new journal and one per-Run tracker.
    path = tmp_path / "actual-usage-journal.jsonl"
    journal = T17LiveUsageJournal(path, _binding())
    journal.open_new()
    tracker = journal.start_unit(
        "unit-1",
        "trial-1",
        T17LiveUnitKind.CORE,
    )

    # When: a reservation, response and completed terminal are persisted.
    budget = _budget()
    tracker.record_attempt(budget)
    tracker.record_detailed_response(
        ActualResponseUsage(
            token_usage=_usage(),
            estimated_cost_usd=Decimal("0.001"),
            provider="openai",
            model_id="gpt-5.6-luna",
            model_revision="gpt-5.6-luna",
            budget=budget,
        )
    )
    tracker.finalize(
        ReferenceLiveTelemetry(
            api_call_count=1,
            response_count=1,
            agent_step_count=1,
            retry_count=0,
            refusal_count=0,
            no_call_count=0,
            token_usage=_usage(),
            latency_ms=12,
            estimated_cost_usd=Decimal("0.001"),
            conservative_reserved_usd=Decimal("0.01"),
        ),
        T17LiveTerminalStatus.COMPLETED,
    )

    # Then: sequence and forward hashes verify, with no secret/prompt field.
    events = load_live_journal(path)
    assert tuple(item.event_type for item in events) == (
        "attempt",
        "response",
        "terminal",
    )
    raw = path.read_text(encoding="utf-8")
    assert "api-key-marker" not in raw
    assert '"prompt"' not in raw
    assert '"output_text"' not in raw


def test_live_usage_journal_detects_tampering(tmp_path: Path) -> None:
    path = tmp_path / "actual-usage-journal.jsonl"
    journal = T17LiveUsageJournal(path, _binding())
    journal.open_new()
    tracker = journal.start_unit("unit-1", "trial-1", T17LiveUnitKind.CORE)
    tracker.record_attempt(_budget())
    path.write_text(
        path.read_text(encoding="utf-8").replace('"api_call_count":1', '"api_call_count":2'),
        encoding="utf-8",
    )

    with pytest.raises(T17LiveJournalError):
        load_live_journal(path)


def test_live_usage_journal_persists_revision_before_stopping(
    tmp_path: Path,
) -> None:
    path = tmp_path / "actual-usage-journal.jsonl"
    journal = T17LiveUsageJournal(path, _binding())
    journal.open_new()
    tracker = journal.start_unit("unit-1", "trial-1", T17LiveUnitKind.CORE)
    budget = _budget()
    tracker.record_attempt(budget)

    with pytest.raises(T17ModelRevisionDriftError):
        tracker.record_detailed_response(
            ActualResponseUsage(
                token_usage=_usage(),
                estimated_cost_usd=Decimal("0.001"),
                provider="openai",
                model_id="gpt-5.6-luna",
                model_revision="gpt-5.6-luna-drift",
                budget=budget,
            )
        )

    assert load_live_journal(path)[-1].actual_model_revision == "gpt-5.6-luna-drift"


def test_live_journal_errors_allow_runtime_traceback_binding() -> None:
    error = T17LiveJournalError(T17LiveJournalErrorCode.HASH_INVALID)

    error.__traceback__ = None

    assert error.__traceback__ is None
