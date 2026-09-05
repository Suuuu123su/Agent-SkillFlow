import json
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import SecretStr

from skillflow.experiment.t16.openai_response_models import JsonObject
from skillflow.experiment.t16.openai_responses import TransportResponse
from skillflow.experiment.t17.reference_backend import ReferenceModelRequest
from skillflow.experiment.t17.v2.api_models import (
    CallIdentity,
    V2BudgetExhaustedError,
    V2LiveConfig,
)
from skillflow.experiment.t19.live import T19LiveClient
from skillflow.experiment.t19.usage import read_usage
from skillflow.models.references import FixtureImplementationRef

ROOT = Path(__file__).resolve().parents[3]


class LocalTransport:
    calls = 0

    def post_json(
        self, url: str, headers: Mapping[str, str], payload: JsonObject
    ) -> TransportResponse:
        self.calls += 1
        return TransportResponse(
            200,
            {
                "id": "test_" + str(self.calls),
                "model": "deepseek-v4-flash",
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "id": "message",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(
                                    {
                                        "selected_action_ids": [],
                                        "output_text": "local result",
                                        "output_mime_type": "text/plain",
                                    }
                                ),
                            }
                        ],
                    }
                ],
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 30,
                    "total_tokens": 130,
                    "input_tokens_details": {"cached_tokens": 20},
                    "output_tokens_details": {"reasoning_tokens": 10},
                },
            },
            1,
        )


def client_for(path: Path, previous: Decimal = Decimal(0)) -> tuple[T19LiveClient, LocalTransport]:
    data = json.loads((ROOT / "experiments/t19/model-reference.json").read_text())
    data["budget"].update(max_total_usd="35", max_retries=0)
    data["max_input_bytes"] = 12000
    transport = LocalTransport()
    client = T19LiveClient(V2LiveConfig.model_validate(data), SecretStr("test-only"), transport)
    client.open_accounted_journal(path / "usage.jsonl", "a" * 64, previous)
    return client, transport


def request(client: T19LiveClient, session: str) -> None:
    client.bind_call(
        CallIdentity(run_id="run", session_id=session, step_id="step", call_id=session)
    )
    client.decide(
        ReferenceModelRequest(
            FixtureImplementationRef("fixture://local"),
            (),
            (),
            "opaque-task",
            "local task",
            "local result",
        )
    )


def test_replay_prefix_and_sessions_cannot_reset_steps(tmp_path: Path) -> None:
    client, transport = client_for(tmp_path, Decimal(2))
    client.begin_replay("branch", 15)
    request(client, "session-1")
    with pytest.raises(V2BudgetExhaustedError, match="agent_turns"):
        request(client, "session-3")
    assert transport.calls == 1
    assert client.unit_usage().api_calls == 1
    assert client.total_reserved_usd() > 2
    assert client.prefix_steps("branch", frozenset({"session-1"})) == 1


def test_previous_unknown_reservation_blocks_next_chain(tmp_path: Path) -> None:
    client, transport = client_for(tmp_path, Decimal("34.99"))
    with pytest.raises(V2BudgetExhaustedError, match="next_unit_worst_cost"):
        client.begin_unit("new")
    assert transport.calls == 0
    assert client.total_reserved_usd() == Decimal("34.99")


@pytest.mark.parametrize("steps", [-1, 16, 17])
def test_invalid_prefix_does_not_open_a_unit(tmp_path: Path, steps: int) -> None:
    client, transport = client_for(tmp_path)
    with pytest.raises(ValueError, match="prefix_out_of_bounds"):
        client.begin_replay("new", steps)
    assert transport.calls == 0


def test_unregistered_repeat_is_rejected_by_audit(tmp_path: Path) -> None:
    client, _ = client_for(tmp_path)
    client.begin_unit("core")
    request(client, "same-call")
    request(client, "same-call")
    with pytest.raises(ValueError, match="model_result_resampled"):
        read_usage(tmp_path / "usage.jsonl", tmp_path)


def test_registered_recovery_is_counted_without_resetting_budget(tmp_path: Path) -> None:
    client, transport = client_for(tmp_path)
    client.begin_unit("core")
    request(client, "same-call")
    client.record_recovery_intent(("simulated-blocked-argument",), ("simulated-blocked-action",))
    request(client, "same-call")
    rows = read_usage(tmp_path / "usage.jsonl", tmp_path)
    assert sum(e.event_type == "attempt" for e in rows) == transport.calls == 2
    assert client.unit_usage().api_calls == 2


def test_recovery_registration_requires_actual_current_response(tmp_path: Path) -> None:
    client, _ = client_for(tmp_path)
    client.begin_unit("core")
    with pytest.raises(ValueError, match="without_completed_blocked_call"):
        client.record_recovery_intent(("not-produced",), ("not-run",))
