"""已发送但没有完整响应的请求，不得把已知用量下界说成完整用量。"""

from decimal import Decimal
from pathlib import Path

import pytest
from tests.unit.experiment.t17.test_v2_live_client import FakeTransport, _client, _request

from skillflow.experiment.t16.budget import CallReservation
from skillflow.experiment.t17.v2.api_models import CallIdentity
from skillflow.experiment.t17.v2.campaign_usage import journal_totals
from skillflow.experiment.t17.v2.journal import V2UsageJournal, read_journal


@pytest.mark.parametrize("reason", [None, "timeout", "usage_unavailable"])
def test_interrupted_request_usage_is_incomplete_and_keeps_reservation(
    tmp_path: Path, reason: str | None
) -> None:
    config = _client(tmp_path, FakeTransport()).config
    journal = V2UsageJournal(tmp_path / "interrupted.jsonl", config, "d" * 64)
    journal.begin_unit("interrupted-unit")
    journal.call = CallIdentity(run_id="r", session_id="s", step_id="step", call_id="call")
    budget = journal.ledger.authorize_call(
        CallReservation(estimated_cost_usd=Decimal("0.02"), max_output_tokens=2048)
    )
    journal.record_attempt(budget)
    if reason is not None:
        journal.append("transport_failure", reason=reason, latency_ms=50)
    for usage in (journal.usage(), journal_totals(read_journal(journal.path))):
        assert not usage.complete
        assert usage.missing_reason
        assert usage.api_calls == 1
        assert usage.responses == 0
        assert usage.reserved_cost_usd == Decimal("0.02")
        assert usage.estimated_cost_usd == 0


def test_successful_retry_does_not_erase_unknown_first_response(tmp_path: Path) -> None:
    client = _client(tmp_path, FakeTransport(timeout=True))
    client.decide(_request())
    for usage in (client.unit_usage(), journal_totals(read_journal(tmp_path / "usage.jsonl"))):
        assert not usage.complete
        assert usage.missing_reason == "timeout"
        assert usage.api_calls == 2
        assert usage.responses == 1
        assert usage.estimated_cost_usd > 0
        assert usage.reserved_cost_usd > usage.estimated_cost_usd
