"""第二版唯一真实网络边界：固定地址、无重定向、无隐式重试。"""

import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager

import httpx2
from pydantic import JsonValue, TypeAdapter, ValidationError

from skillflow.experiment.t16.openai_response_models import JsonObject
from skillflow.experiment.t16.openai_responses import (
    HTTP_SUCCESS_MAX,
    HTTP_SUCCESS_MIN,
    OpenAIResponsesError,
    OpenAIResponsesErrorKind,
    TransportResponse,
)
from skillflow.experiment.t17.v2.api_models import V2ProviderFailureError, V2UsageUnavailableError

_ENDPOINT = "https://api.openai.com/v1/responses"
_ALLOWED_ENDPOINTS = {_ENDPOINT, "https://api.deepseek.com/responses"}
_JSON_OBJECT = TypeAdapter(dict[str, JsonValue])


class FixedEndpointTransport:
    """即使注入的客户端允许跳转，也不能将请求或凭据发往其他地址。"""

    def __init__(self, client: httpx2.Client, endpoint: str = _ENDPOINT) -> None:
        """接收可以被完全本地替换的客户端。"""
        if endpoint not in _ALLOWED_ENDPOINTS:
            raise V2ProviderFailureError("v2_network_endpoint_not_allowed")
        self._client, self._endpoint = client, endpoint

    def post_json(
        self, url: str, headers: Mapping[str, str], payload: JsonObject
    ) -> TransportResponse:
        """仅连接失败和超时交给有预算的显式重试层。"""
        if url != self._endpoint:
            raise V2ProviderFailureError("v2_network_endpoint_not_allowed")
        started = time.perf_counter()
        try:
            response = self._client.post(url, headers=headers, json=payload, follow_redirects=False)
        except httpx2.TimeoutException as error:
            raise OpenAIResponsesError(OpenAIResponsesErrorKind.TIMEOUT) from error
        except httpx2.ConnectError as error:
            raise OpenAIResponsesError(OpenAIResponsesErrorKind.PROVIDER_ERROR) from error
        except httpx2.RequestError as error:
            raise V2ProviderFailureError("v2_network_response_state_unknown") from error
        latency = max(0, round((time.perf_counter() - started) * 1000))
        try:
            body = _JSON_OBJECT.validate_python(response.json())
        except (ValueError, ValidationError) as error:
            if HTTP_SUCCESS_MIN <= response.status_code < HTTP_SUCCESS_MAX:
                raise V2UsageUnavailableError("v2_network_response_not_json_object") from error
            body = {}
        return TransportResponse(response.status_code, body, latency)


@contextmanager
def managed_transport(endpoint: str = _ENDPOINT) -> Iterator[FixedEndpointTransport]:
    """同一监督进程复用连接，但不读取环境代理或自动跳转。"""
    limits = httpx2.Limits(max_connections=4, max_keepalive_connections=4, keepalive_expiry=30)
    transport = httpx2.HTTPTransport(http2=True, retries=0, limits=limits, trust_env=False)
    timeout = httpx2.Timeout(connect=10, read=120, write=10, pool=10)
    with httpx2.Client(
        transport=transport, timeout=timeout, follow_redirects=False, trust_env=False
    ) as client:
        yield FixedEndpointTransport(client, endpoint)
