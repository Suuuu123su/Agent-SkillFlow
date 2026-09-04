"""新尝试不能重置已经消耗的阶段预算或总预算。"""

from decimal import Decimal

import pytest

from skillflow.experiment.t16.budget import BudgetConfig
from skillflow.experiment.t17.live_matrix import T17LiveStage
from skillflow.experiment.t17.v2.campaign_limits import SpendingHistory, remaining_budget
from skillflow.experiment.t17.v2.campaign_models import StageOutcome
from skillflow.experiment.t17.v2.run_models import UnitUsage


def _failed(amount: str, path: str = "local/failed-01") -> StageOutcome:
    return StageOutcome(
        stage=T17LiveStage.CANARY,
        status="failed",
        reason="worker_exit",
        raw_relative_path=path,
        usage=UnitUsage(
            complete=False, missing_reason="unclosed_attempt", reserved_cost_usd=Decimal(amount)
        ),
    )


def _budget() -> BudgetConfig:
    return BudgetConfig(
        max_total_usd=Decimal("0.25"),
        max_cost_per_run_usd=Decimal("0.05"),
        max_agent_turns=16,
        max_output_tokens_per_turn=2048,
        max_retries=1,
    )


def test_restart_deducts_failed_reservations_and_never_raises_unit_cap() -> None:
    history = SpendingHistory((), (_failed("0.02"),))
    budget = remaining_budget(T17LiveStage.CANARY, _budget(), Decimal("58.25"), history)
    assert budget.max_total_usd == Decimal("0.23")
    assert budget.max_cost_per_run_usd == Decimal("0.05")
    assert history.reserved_usd == Decimal("0.02")


def test_total_cap_is_shared_and_duplicate_attempts_are_rejected() -> None:
    history = SpendingHistory((), (_failed("0.02"),))
    budget = remaining_budget(T17LiveStage.CANARY, _budget(), Decimal("0.03"), history)
    assert budget.max_total_usd == budget.max_cost_per_run_usd == Decimal("0.01")
    with pytest.raises(ValueError, match="v2_budget_exhausted"):
        remaining_budget(T17LiveStage.CANARY, _budget(), Decimal("0.02"), history)
    with pytest.raises(ValueError, match="v2_duplicate_attempt_accounting"):
        SpendingHistory((), (_failed("0.02"), _failed("0.02")))
