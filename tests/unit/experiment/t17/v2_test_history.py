"""用于费用回归的纯合成旧格式日志，不依赖本地私有历史记录。"""

from decimal import Decimal
from pathlib import Path

from skillflow.experiment.t16.budget import BudgetLedger, CallReservation
from skillflow.experiment.t16.provider import TokenUsage
from skillflow.experiment.t17.live_attempt_models import T17LiveUnitKind
from skillflow.experiment.t17.live_journal import T17LiveUsageJournal
from skillflow.experiment.t17.live_journal_models import T17LiveJournalBinding
from skillflow.experiment.t17.live_matrix import T17LiveStage, load_live_preregistration


def write_history(path: Path) -> None:
    journal = T17LiveUsageJournal(
        path,
        T17LiveJournalBinding(
            phase_contract_sha256="a" * 64,
            approved_config_sha256="b" * 64,
            stage=T17LiveStage.CANARY,
            model_id="gpt-5.6-luna",
            model_revision="gpt-5.6-luna",
        ),
    )
    journal.open_new()
    config = load_live_preregistration(Path("experiments/t17/preregistration.yaml"))
    budget = BudgetLedger(config.model1_budget.model_copy(update={"allow_live": True}))
    tracker = journal.start_unit("simulated-history", "simulated-trial", T17LiveUnitKind.CORE)
    for inputs in (10, 20):
        budget = budget.authorize_call(
            CallReservation(estimated_cost_usd=Decimal("0.001"), max_output_tokens=10)
        )
        tracker.record_attempt(budget)
        tracker.record_response(
            TokenUsage(
                input_tokens=inputs, cached_input_tokens=0, output_tokens=2, reasoning_tokens=1
            ),
            Decimal("0.0001"),
        )
