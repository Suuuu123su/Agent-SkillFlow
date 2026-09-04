"""费用与科学样本分母分开，失败记录不能因撤回丢失或重复计费。"""

from decimal import Decimal
from pathlib import Path

import pytest

from skillflow.experiment.t17.v2.run_models import UnitUsage


def test_all_closed_attempts_include_failed_costs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[4] / "scripts/t17_delivery"))
    from t17_costs import ExpenseRow, summed_usage  # noqa: PLC0415

    rows = tuple(
        ExpenseRow(
            source_document=f"attempt-{index}.json",
            source_item="outcome",
            cohort="test",
            stage="model2",
            attempt=index,
            outcome_status="passed" if complete else "failed",
            usage=UnitUsage(
                complete=complete,
                missing_reason=None if complete else "timeout",
                api_calls=2,
                responses=2 if complete else 1,
                estimated_cost_usd=Decimal(1),
                reserved_cost_usd=Decimal("1.5"),
            ),
        )
        for index, complete in enumerate((False, True), 1)
    )
    result = summed_usage(rows)
    assert result.api_calls == 4
    assert result.responses == 3
    assert result.estimated_cost_usd == Decimal(2)
    assert result.reserved_cost_usd == Decimal(3)
    assert not result.complete
    with pytest.raises(ValueError, match="expense_duplicate_source"):
        summed_usage((rows[0], rows[0]))
