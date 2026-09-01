from datetime import UTC, datetime
from pathlib import Path

from skillflow.experiment.t16.budget import BudgetLedger
from skillflow.experiment.t16.task_success_live_agent import (
    TaskSuccessLiveExecutionOptions,
    execute_task_success_live_trial,
)
from skillflow.experiment.t16.task_success_live_config import build_t16d2_live_config
from skillflow.experiment.t16.task_success_live_design import (
    build_task_success_live_design,
)
from skillflow.experiment.t16.task_success_live_mock import TaskSuccessMockLiveClient
from skillflow.experiment.t16.task_success_live_preflight import load_t16d2_inputs

ROOT = Path(__file__).parents[4]


def test_all_48_frozen_trials_complete_the_live_bridge_without_network() -> None:
    inputs = load_t16d2_inputs(ROOT)
    config = build_t16d2_live_config(ROOT)
    by_condition = {item.condition_id: item for item in inputs.registry.conditions}
    budget = BudgetLedger(config.budget)
    executions = []

    for ordinal, trial in enumerate(inputs.matrix.trials):
        design = build_task_success_live_design(inputs, trial)
        execution = execute_task_success_live_trial(
            design,
            by_condition[trial.condition_id],
            config,
            TaskSuccessMockLiveClient(),
            budget.begin_run(),
            TaskSuccessLiveExecutionOptions(
                run_id=f"mock-attempt--{trial.trial_id}",
                created_at=datetime(2026, 8, 29, 0, ordinal, tzinfo=UTC),
                phase_contract_sha256="2" * 64,
            ),
        )
        executions.append(execution)
        budget = execution.budget

    assert len(executions) == 48
    assert len({item.record.result.trial_id for item in executions}) == 48
    assert all(item.record.task_success_result is not None for item in executions)
    assert all(
        item.record.task_success_result.not_evaluable_assertion_ids == ()
        for item in executions
        if item.record.task_success_result is not None
    )
    assert all(item.record.result.task_success is True for item in executions)
    assert all(
        item.provider_model_revisions
        == tuple("gpt-5.6-luna" for _ in item.provider_model_revisions)
        for item in executions
    )
