import uuid

import httpx2
import pytest

from skillflow.experiment.t16.httpx2_transport import Httpx2ResponsesTransport
from skillflow.experiment.t16.openai_responses import (
    OpenAIResponsesError,
    OpenAIResponsesErrorKind,
)

TIMEOUT_MESSAGE = "timed out"


def test_httpx2_transport_uses_injected_client_without_real_network() -> None:
    observed: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        observed.append(request)
        return httpx2.Response(200, json={"ok": True})

    with httpx2.Client(transport=httpx2.MockTransport(handler)) as client:
        result = Httpx2ResponsesTransport(client).post_json(
            "https://api.openai.com/v1/responses",
            {"authorization": "Bearer masked"},
            {"model": "gpt-5.6-luna"},
        )

    assert result.status_code == 200
    assert result.body == {"ok": True}
    assert result.latency_ms >= 0
    assert observed[0].url == "https://api.openai.com/v1/responses"


def test_httpx2_transport_maps_timeout_without_leaking_headers() -> None:
    marker_text = str(uuid.UUID(int=54321))

    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout(TIMEOUT_MESSAGE, request=request)

    with (
        httpx2.Client(transport=httpx2.MockTransport(handler)) as client,
        pytest.raises(OpenAIResponsesError) as captured,
    ):
        Httpx2ResponsesTransport(client).post_json(
            "https://api.openai.com/v1/responses",
            {"authorization": f"Bearer {marker_text}"},
            {"model": "gpt-5.6-luna"},
        )

    assert captured.value.kind is OpenAIResponsesErrorKind.TIMEOUT
    assert marker_text not in str(captured.value)


def test_httpx2_transport_rejects_non_object_json() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=["not", "an", "object"])

    with (
        httpx2.Client(transport=httpx2.MockTransport(handler)) as client,
        pytest.raises(OpenAIResponsesError) as captured,
    ):
        Httpx2ResponsesTransport(client).post_json(
            "https://api.openai.com/v1/responses",
            {},
            {"model": "gpt-5.6-luna"},
        )

    assert captured.value.kind is OpenAIResponsesErrorKind.PROVIDER_ERROR
