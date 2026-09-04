"""DeepSeek 最小接入验证：主机隔离、指令角色、用量；不连接网络。"""

from collections.abc import Mapping
from pathlib import Path

import httpx2
import pytest
from pydantic import SecretStr, ValidationError

from skillflow.experiment.t16.openai_response_models import JsonObject
from skillflow.experiment.t16.openai_responses import TransportResponse
from skillflow.experiment.t17.v2.api_models import (
    CallIdentity,
    V2LiveConfig,
    V2ProviderFailureError,
)
from skillflow.experiment.t17.v2.live_client import V2LiveClient
from skillflow.experiment.t17.v2.network import FixedEndpointTransport
from skillflow.experiment.t17.v2.prompt_contract import input_items

from .test_v2_live_client import FakeTransport, _client, _request

DS = "https://api.deepseek.com/responses"
OPENAI = "https://api.openai.com/v1/responses"


class DeepSeekFake(FakeTransport):
    def post_json(
        self, url: str, headers: Mapping[str, str], payload: JsonObject
    ) -> TransportResponse:
        assert url == DS
        assert payload["model"] == "deepseek-v4-flash"
        assert payload["input"][0]["role"] == "system"
        assert payload["input"][0]["content"] == input_items(_request())[0]["content"]
        assert payload["reasoning"] == {"effort": "medium"}
        response = super().post_json(url, headers, payload)
        return TransportResponse(
            response.status_code,
            {
                **response.body,
                "model": "deepseek-v4-flash",
            },
            response.latency_ms,
        )


def test_deepseek_request_role_and_accounting(tmp_path: Path) -> None:
    base = _client(tmp_path, FakeTransport()).config
    data = base.model_dump()
    data["provider"].update(model_id="deepseek-v4-flash", model_revision="deepseek-v4-flash")
    data.update(endpoint=DS, prompt_cache_mode="automatic")
    client = V2LiveClient(V2LiveConfig.model_validate(data), SecretStr("fake-only"), DeepSeekFake())
    client.open_journal(tmp_path / "deepseek-usage.jsonl", "d" * 64)
    client.begin_unit("ds-unit")
    client.bind_call(CallIdentity(run_id="r", session_id="s", step_id="step", call_id="call"))
    assert client.decide(_request()).selected_action_ids == ("read-report",)
    assert client.unit_usage().responses == 1
    assert client.unit_usage().reasoning_tokens == 10
    assert input_items(_request())[0]["role"] == "developer"
    data["endpoint"] = OPENAI
    with pytest.raises(ValidationError, match="v2_provider_endpoint_mismatch"):
        V2LiveConfig.model_validate(data)


@pytest.mark.parametrize(("endpoint", "wrong"), [(DS, OPENAI), (OPENAI, DS)])
def test_deepseek_key_cannot_cross_platform(endpoint: str, wrong: str) -> None:
    visited = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        visited.append(str(request.url))
        return httpx2.Response(307, headers={"location": wrong}, json={})

    with httpx2.Client(transport=httpx2.MockTransport(handler), follow_redirects=True) as client:
        transport = FixedEndpointTransport(client, endpoint)
        with pytest.raises(V2ProviderFailureError):
            transport.post_json(wrong, {"authorization": "Bearer fake"}, {})
        assert not visited
        assert transport.post_json(endpoint, {}, {}).status_code == 307
        assert visited == [endpoint]
