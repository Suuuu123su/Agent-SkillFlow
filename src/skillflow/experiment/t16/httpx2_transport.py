"""T16-C 唯一允许的 httpx2 真实网络传输。"""

import socket
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager

import httpx2
from pydantic import JsonValue, TypeAdapter, ValidationError

from skillflow.experiment.t16.openai_response_models import JsonObject
from skillflow.experiment.t16.openai_responses import (
    OpenAIResponsesError,
    OpenAIResponsesErrorKind,
    TransportResponse,
)

_JSON_OBJECT = TypeAdapter(dict[str, JsonValue])
_LIMITS = httpx2.Limits(
    max_connections=50,
    max_keepalive_connections=20,
    keepalive_expiry=30.0,
)
_TIMEOUT = httpx2.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0)
_SOCKET_OPTIONS = [(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)]


class Httpx2ResponsesTransport:
    """把注入的 httpx2 Client 收窄为 ResponsesTransport。"""

    def __init__(self, client: httpx2.Client) -> None:
        """保存显式注入且可由 MockTransport 替换的 Client。"""
        self._client = client

    def post_json(
        self,
        url: str,
        headers: Mapping[str, str],
        payload: JsonObject,
    ) -> TransportResponse:
        """发送一次无自动重试请求并验证 JSON 根对象。"""
        started = time.perf_counter()
        try:
            response = self._client.post(url, headers=headers, json=payload)
        except httpx2.TimeoutException as error:
            raise OpenAIResponsesError(OpenAIResponsesErrorKind.TIMEOUT) from error
        except httpx2.RequestError as error:
            raise OpenAIResponsesError(OpenAIResponsesErrorKind.PROVIDER_ERROR) from error
        latency_ms = max(0, round((time.perf_counter() - started) * 1000))
        try:
            body = _JSON_OBJECT.validate_python(response.json())
        except (ValidationError, ValueError) as error:
            raise OpenAIResponsesError(
                OpenAIResponsesErrorKind.PROVIDER_ERROR,
                response.status_code,
            ) from error
        return TransportResponse(response.status_code, body, latency_ms)


@contextmanager
def managed_httpx2_transport() -> Iterator[Httpx2ResponsesTransport]:
    """建立固定 OpenAI 单主机连接池；传输重试为零。"""
    transport = httpx2.HTTPTransport(
        http2=True,
        retries=0,
        limits=_LIMITS,
        socket_options=_SOCKET_OPTIONS,
    )
    with httpx2.Client(
        transport=transport,
        timeout=_TIMEOUT,
        follow_redirects=True,
        trust_env=False,
        event_hooks={"request": [_mark_start], "response": [_mark_elapsed]},
    ) as client:
        yield Httpx2ResponsesTransport(client)


def _mark_start(request: httpx2.Request) -> None:
    request.extensions["skillflow_request_started"] = time.perf_counter()


def _mark_elapsed(response: httpx2.Response) -> None:
    started = response.request.extensions.get("skillflow_request_started")
    if isinstance(started, float):
        response.extensions["skillflow_elapsed_ms"] = max(
            0,
            round((time.perf_counter() - started) * 1000),
        )
