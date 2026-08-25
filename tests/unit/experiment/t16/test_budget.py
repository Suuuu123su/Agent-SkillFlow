from decimal import Decimal

import pytest

from skillflow.experiment.t16.budget import (
    BudgetConfig,
    BudgetExceededError,
    BudgetLedger,
    BudgetLimit,
    CallReservation,
)


def budget_config(**changes: object) -> BudgetConfig:
    payload = {
        "max_total_usd": Decimal("1.00"),
        "max_cost_per_run_usd": Decimal("0.60"),
        "max_agent_turns": 2,
        "max_output_tokens_per_turn": 100,
        "max_retries": 2,
    }
    payload.update(changes)
    return BudgetConfig.model_validate(payload)


def reservation(cost: str = "0.20", output: int = 100) -> CallReservation:
    return CallReservation(estimated_cost_usd=Decimal(cost), max_output_tokens=output)


def test_live_is_disabled_by_default() -> None:
    # Given / When: 未显式配置 live 的预算。
    config = budget_config()

    # Then: 默认关闭真实调用。
    assert config.allow_live is False


def test_budget_stops_before_exceeding_run_total_and_turn_limits() -> None:
    # Given: 一条允许两次调用、单 Run 0.60 美元的预算。
    ledger = BudgetLedger(budget_config())
    ledger = ledger.authorize_call(reservation("0.30"))
    ledger = ledger.authorize_call(reservation("0.30"))

    # When / Then: 上限本身可达，下一次调用立即停止。
    assert ledger.run_spent_usd == Decimal("0.60")
    with pytest.raises(BudgetExceededError) as error:
        ledger.authorize_call(reservation("0.01"))
    assert error.value.limit is BudgetLimit.RUN_COST

    turn_limited = BudgetLedger(budget_config(max_cost_per_run_usd=Decimal("1.00")))
    turn_limited = turn_limited.authorize_call(reservation("0"))
    turn_limited = turn_limited.authorize_call(reservation("0"))
    with pytest.raises(BudgetExceededError) as turn_error:
        turn_limited.authorize_call(reservation("0"))
    assert turn_error.value.limit is BudgetLimit.AGENT_TURNS


def test_budget_stops_on_output_total_and_retry_limits() -> None:
    # Given: 一个新预算状态。
    ledger = BudgetLedger(budget_config())

    # When / Then: 单轮输出不能超过硬上限。
    with pytest.raises(BudgetExceededError) as output_error:
        ledger.authorize_call(reservation(output=101))
    assert output_error.value.limit is BudgetLimit.OUTPUT_TOKENS

    total_limited = BudgetLedger(
        budget_config(max_total_usd=Decimal("0.30"), max_cost_per_run_usd=Decimal("0.30"))
    )
    total_limited = total_limited.authorize_call(reservation("0.30"))
    total_limited = total_limited.begin_run()
    with pytest.raises(BudgetExceededError) as total_error:
        total_limited.authorize_call(reservation("0.01"))
    assert total_error.value.limit is BudgetLimit.TOTAL_COST

    ledger = ledger.record_retry().record_retry()
    with pytest.raises(BudgetExceededError) as retry_error:
        ledger.record_retry()
    assert retry_error.value.limit is BudgetLimit.RETRIES


def test_begin_run_preserves_total_and_resets_local_counters() -> None:
    # Given: 已消耗调用与重试的状态。
    ledger = BudgetLedger(budget_config()).authorize_call(reservation()).record_retry()

    # When: 开始下一条实验链。
    next_run = ledger.begin_run()

    # Then: 总费用保留，局部计数清零。
    assert next_run.total_spent_usd == Decimal("0.20")
    assert next_run.run_spent_usd == Decimal(0)
    assert next_run.agent_turns == 0
    assert next_run.retries == 0
