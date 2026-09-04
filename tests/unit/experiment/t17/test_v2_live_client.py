"""所有响应先保存用量；模型拒绝和格式失败不重采样。"""

import json
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import SecretStr

from skillflow.experiment.t16.budget import BudgetConfig
from skillflow.experiment.t16.openai_response_models import JsonObject
from skillflow.experiment.t16.openai_responses import (
    OpenAIResponsesError,
    OpenAIResponsesErrorKind,
    TransportResponse,
)
from skillflow.experiment.t17.live_matrix import load_live_preregistration
from skillflow.experiment.t17.reference_backend import ReferenceModelRequest
from skillflow.experiment.t17.v2.api_models import (
    CallIdentity,
    V2LiveConfig,
    V2ProviderFailureError,
    V2RevisionDriftError,
)
from skillflow.experiment.t17.v2.journal import V2UsageJournal, read_journal
from skillflow.experiment.t17.v2.live_client import V2LiveClient
from skillflow.experiment.t17.v2.runtime_models import ModelOutcomeError
from skillflow.models.references import FixtureImplementationRef


class FakeTransport:
    def __init__(
        self,
        *,
        malformed: bool = False,
        drift: bool = False,
        status: int = 200,
        timeout: bool = False,
        envelope: bool = False,
    ) -> None:
        self.calls = 0
        self.malformed, self.drift, self.status, self.timeout, self.envelope = (
            malformed,
            drift,
            status,
            timeout,
            envelope,
        )

    def post_json(
        self, url: str, headers: Mapping[str, str], payload: JsonObject
    ) -> TransportResponse:
        self.calls += 1
        assert "temperature" not in payload
        if self.timeout and self.calls == 1:
            raise OpenAIResponsesError(OpenAIResponsesErrorKind.TIMEOUT)
        output = {"selected_action_ids": ["read-report"], "output_text": "summary"}
        if self.malformed:
            output["origin_ids"] = ["forged"]
        body = {
            "id": "resp_test_" + str(self.calls),
            "model": "gpt-5.5-2026-04-23" if self.drift else "gpt-5.6-luna",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "id": "msg_1",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": json.dumps(output)}],
                }
            ],
            "usage": {
                "input_tokens": 100,
                "output_tokens": 30,
                "total_tokens": 130,
                "input_tokens_details": {"cached_tokens": 20},
                "output_tokens_details": {"reasoning_tokens": 10},
            },
        }
        if self.envelope:
            body["output"] = [{"type": "unrecognized-output"}]
        return TransportResponse(self.status, body, 4321)


def _client(tmp_path: Path, transport: FakeTransport) -> V2LiveClient:
    old = load_live_preregistration(Path("experiments/t17/preregistration.yaml"))
    config = V2LiveConfig(
        provider=old.model1_provider,
        budget=BudgetConfig(
            allow_live=True,
            max_total_usd=Decimal(10),
            max_cost_per_run_usd=Decimal(1),
            max_agent_turns=16,
            max_output_tokens_per_turn=2048,
            max_retries=1,
        ),
        matrix_sha256="a" * 64,
        cost_plan_sha256="b" * 64,
        approval_id="test-only-approval",
        prompt_cache_mode="explicit",
    )
    client = V2LiveClient(config, SecretStr("unit-test-not-a-real-key"), transport)
    client.open_journal(tmp_path / "usage.jsonl", "c" * 64)
    client.begin_unit("unit-1")
    client.bind_call(
        CallIdentity(run_id="run-1", session_id="session-1", step_id="step-1", call_id="call-1")
    )
    return client


def _request() -> ReferenceModelRequest:
    return ReferenceModelRequest(
        FixtureImplementationRef("fixture://test"),
        (),
        ("read-report",),
        "unused-label",
        "读取报告",
        "summary",
    )


@pytest.mark.parametrize("envelope", [False, True])
def test_bad_schema_keeps_usage_latency_without_resampling(tmp_path: Path, envelope: bool) -> None:
    transport = FakeTransport(malformed=not envelope, envelope=envelope)
    client = _client(tmp_path, transport)
    with pytest.raises(ModelOutcomeError, match="schema_rejection"):
        client.decide(_request())
    events = read_journal(tmp_path / "usage.jsonl")
    responses = [e for e in events if e.event_type == "response"]
    assert len(responses) == transport.calls == 1
    assert responses[0].latency_ms == 4321
    assert responses[0].usage.reasoning_tokens == 10
    assert client.unit_usage().responses == 1
    assert client.unit_usage().estimated_cost_usd > 0
    assert "forged" not in (tmp_path / "usage.jsonl").read_text(encoding="utf-8")
    assert "unit-test-not-a-real-key" not in (tmp_path / "usage.jsonl").read_text(encoding="utf-8")


def test_transient_retry_preserves_failed_reservation(tmp_path: Path) -> None:
    transport = FakeTransport(timeout=True)
    client = _client(tmp_path, transport)
    assert client.decide(_request()).selected_action_ids == ("read-report",)
    assert transport.calls == client.unit_usage().api_calls == 2
    assert client.unit_usage().reserved_cost_usd > client.unit_usage().estimated_cost_usd


def test_deterministic_4xx_is_not_retried(tmp_path: Path) -> None:
    transport = FakeTransport(status=400)
    client = _client(tmp_path, transport)
    with pytest.raises(V2ProviderFailureError):
        client.decide(_request())
    assert transport.calls == 1


def test_revision_drift_is_durable_and_stops(tmp_path: Path) -> None:
    transport = FakeTransport(drift=True)
    client = _client(tmp_path, transport)
    with pytest.raises(V2RevisionDriftError):
        client.decide(_request())
    assert read_journal(tmp_path / "usage.jsonl")[-1].event_type == "revision_drift"
    assert client.unit_usage().responses == 1
    with pytest.raises(V2RevisionDriftError):
        client.decide(_request())
    assert transport.calls == 1


@pytest.mark.parametrize(
    "fault", ["duplicate_attempt", "early_settlement", "phase_drift", "call_drift"]
)
def test_hash_valid_journal_still_rejects_invalid_order(tmp_path: Path, fault: str) -> None:
    config = _client(tmp_path, FakeTransport()).config
    journal = V2UsageJournal(tmp_path / "bad-order.jsonl", config, "c" * 64)
    journal.begin_unit("u1")
    journal.call = CallIdentity(run_id="r", session_id="s", step_id="step", call_id="call")
    journal.record_attempt(journal.ledger)
    if fault == "duplicate_attempt":
        journal.append("attempt")
    elif fault == "early_settlement":
        journal.append("settlement")
    elif fault == "phase_drift":
        journal.append("http_error", reason="http_status_400", phase_contract_sha256="d" * 64)
    else:
        journal.append(
            "http_error",
            reason="http_status_400",
            call=journal.call.model_copy(update={"call_id": "other"}),
        )
    with pytest.raises(ValueError, match="v2_usage_"):
        read_journal(journal.path)
