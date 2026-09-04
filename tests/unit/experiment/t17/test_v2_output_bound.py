"""只对已批准的、完整用量且未超金额预留的 DeepSeek 超限空响应继续终态化。"""

from collections.abc import Mapping
from pathlib import Path

import pytest
from pydantic import SecretStr

from skillflow.experiment.t16.openai_response_models import JsonObject
from skillflow.experiment.t16.openai_responses import TransportResponse
from skillflow.experiment.t17.v2.api_models import (
    CallIdentity,
    V2LiveConfig,
    V2UsageUnavailableError,
)
from skillflow.experiment.t17.v2.journal import read_journal
from skillflow.experiment.t17.v2.live_client import V2LiveClient
from skillflow.experiment.t17.v2.runtime_models import ModelOutcomeError

from .test_v2_live_client import FakeTransport, _client, _request


class OverrunResponse(FakeTransport):
    def __init__(self, generated: int, visible: int, status: str) -> None:
        super().__init__()
        self.generated, self.visible, self.response_status = generated, visible, status

    def post_json(
        self, url: str, headers: Mapping[str, str], payload: JsonObject
    ) -> TransportResponse:
        assert payload["max_output_tokens"] == 2048
        response = super().post_json(url, headers, payload)
        body = {**response.body, "model": "deepseek-v4-flash", "status": self.response_status}
        body["usage"] = {
            "input_tokens": 281,
            "output_tokens": self.generated,
            "total_tokens": 281 + self.generated,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens_details": {"reasoning_tokens": self.generated - self.visible},
        }
        if not self.visible:
            body["output"] = []
        return TransportResponse(200, body, 123)


@pytest.mark.parametrize(
    ("generated", "visible", "status", "accepted"),
    [
        (2049, 0, "incomplete", True),
        (6000, 0, "incomplete", False),
        (2049, 1, "incomplete", False),
        (2049, 0, "completed", False),
    ],
)
def test_output_bound_records_existing_empty_failure_only(
    tmp_path: Path, generated: int, visible: int, status: str, accepted: bool
) -> None:
    data = _client(tmp_path / "base", FakeTransport()).config.model_dump()
    data["provider"].update(model_id="deepseek-v4-flash", model_revision="deepseek-v4-flash")
    data.update(endpoint="https://api.deepseek.com/responses", prompt_cache_mode="automatic")
    transport = OverrunResponse(generated, visible, status)
    client = V2LiveClient(V2LiveConfig.model_validate(data), SecretStr("fake-only"), transport)
    path = tmp_path / "usage.jsonl"
    client.open_journal(path, "d" * 64)
    client.begin_unit("unit-output-bound")
    client.bind_call(CallIdentity(run_id="r", session_id="s", step_id="step", call_id="call"))
    expected = ModelOutcomeError if accepted else V2UsageUnavailableError
    with pytest.raises(expected):
        client.decide(_request())
    events = read_journal(path)
    assert transport.calls == 1
    assert client.unit_usage().responses == 1
    assert client.unit_usage().reasoning_tokens == generated - visible
    assert events[-1].event_type == ("model_failure" if accepted else "settlement")
    assert client.config.budget.max_output_tokens_per_turn == 2048
