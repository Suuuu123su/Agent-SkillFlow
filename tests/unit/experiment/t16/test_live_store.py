from decimal import Decimal
from pathlib import Path

import pytest
from tests.unit.experiment.t16.test_live_agent import (
    ScriptedClient,
    _config,
    _design,
    _final_turn,
)

from skillflow.experiment.t16.budget import BudgetConfig, BudgetLedger, CallReservation
from skillflow.experiment.t16.live_agent import LiveTrialExecutionOptions, execute_live_trial
from skillflow.experiment.t16.live_records import LiveTrialRecord
from skillflow.experiment.t16.live_store import (
    DuplicateLiveTrialError,
    LiveBudgetJournal,
    LiveResultStore,
)


def test_live_result_store_resumes_valid_records_and_rejects_duplicate(tmp_path: Path) -> None:
    config = _config()
    execution = execute_live_trial(
        _design("c1-p00"),
        config,
        ScriptedClient([_final_turn()]),
        BudgetLedger(config.budget).begin_run(),
    )
    path = tmp_path / "trial-results.jsonl"
    store = LiveResultStore(path)
    store.open(resume=False)
    store.append(execution.record)

    resumed = LiveResultStore(path)
    resumed.open(resume=True)

    assert resumed.completed_trial_ids == {execution.record.result.trial_id}
    assert resumed.read_records() == (execution.record,)
    with pytest.raises(DuplicateLiveTrialError):
        resumed.append(LiveTrialRecord.model_validate(execution.record.model_dump()))


def test_budget_journal_restores_conservative_reserved_total(tmp_path: Path) -> None:
    config = BudgetConfig(
        allow_live=True,
        max_total_usd=Decimal(20),
        max_cost_per_run_usd=Decimal("0.10"),
        max_agent_turns=12,
        max_output_tokens_per_turn=256,
        max_retries=1,
    )
    journal = LiveBudgetJournal(tmp_path / "budget-journal.jsonl", config)
    journal.open(resume=False)
    ledger = (
        BudgetLedger(config)
        .begin_run()
        .authorize_call(
            CallReservation(
                estimated_cost_usd=Decimal("0.0042"),
                max_output_tokens=256,
            )
        )
    )
    journal.record(ledger)

    resumed = LiveBudgetJournal(journal.path, config)
    resumed.open(resume=True)
    restored = resumed.latest_budget()

    assert restored.total_spent_usd == Decimal("0.0042")
    assert restored.agent_turns == 1


def test_budget_checkpoint_is_written_before_client_invocation(tmp_path: Path) -> None:
    config = _config()
    journal = LiveBudgetJournal(tmp_path / "budget-journal.jsonl", config.budget)
    journal.open(resume=False)

    execute_live_trial(
        _design("c1-p00"),
        config,
        ScriptedClient([_final_turn()]),
        BudgetLedger(config.budget).begin_run(),
        LiveTrialExecutionOptions(budget_checkpoint=journal),
    )

    assert journal.latest_budget().agent_turns == 1
    assert journal.latest_budget().total_spent_usd > 0
