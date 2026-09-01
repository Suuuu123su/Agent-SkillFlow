"""OpenAI Responses API 的无 SDK、可注入传输边界。"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum, unique
from typing import Protocol

from pydantic import SecretStr, ValidationError

from skillflow.experiment.t16.openai_response_models import (
    ApiFunctionCall,
    ApiMessage,
    ApiOutputText,
    ApiRefusal,
    ApiResponse,
    JsonObject,
    OpenAIResponsesCall,
)
from skillflow.experiment.t16.provider import TokenUsage

HTTP_RATE_LIMIT = 429
HTTP_TIMEOUTS = frozenset({408, 504})
HTTP_SUCCESS_MIN = 200
HTTP_SUCCESS_MAX = 300
_SAFE_DIAGNOSTIC_TOKEN = re.compile(r"^[A-Za-z0-9_.\-\[\]]{1,128}$")


@dataclass(frozen=True, slots=True)
class TransportResponse:
    """HTTP 传输返回的最小非敏感结果。"""

    status_code: int
    body: JsonObject
    latency_ms: int


class ResponsesTransport(Protocol):
    """允许单元测试完全替换网络。"""

    def post_json(
        self,
        url: str,
        headers: Mapping[str, str],
        payload: JsonObject,
    ) -> TransportResponse:
        """发送 JSON 并返回已解析对象。"""
        ...


@unique
class OpenAIResponsesErrorKind(StrEnum):
    """Provider 错误的最小封闭分类。"""

    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    PROVIDER_ERROR = "provider_error"


@dataclass(frozen=True, slots=True)
class OpenAIResponsesError(RuntimeError):
    """不携带响应正文或凭据的 Provider 错误。"""

    kind: OpenAIResponsesErrorKind
    status_code: int | None = None
    provider_type: str | None = None
    provider_code: str | None = None
    provider_param: str | None = None

    def __str__(self) -> str:
        """返回不包含正文或凭据的稳定诊断。"""
        status = "none" if self.status_code is None else str(self.status_code)
        fields = [f"status={status}"]
        if self.provider_type is not None:
            fields.append(f"type={self.provider_type}")
        if self.provider_code is not None:
            fields.append(f"code={self.provider_code}")
        if self.provider_param is not None:
            fields.append(f"param={self.provider_param}")
        return f"{self.kind.value}:" + ":".join(fields)


@dataclass(frozen=True, slots=True)
class OpenAIResponsesSchemaError(RuntimeError):
    """API 成功响应不满足所需闭包。"""

    def __str__(self) -> str:
        """返回不包含响应正文的稳定诊断。"""
        return "OpenAI Responses 响应未通过结构校验"


@dataclass(frozen=True, slots=True)
class OpenAIResponsesTurn:
    """一次模型轮次的工具请求、文本和实际用量。"""

    response_id: str
    model_revision: str
    status: str
    function_calls: tuple[ApiFunctionCall, ...]
    continuation_items: tuple[JsonObject, ...]
    output_text: str
    refusal: bool
    token_usage: TokenUsage
    latency_ms: int


class OpenAIResponsesClient:
    """只在 HTTP header 中展开 SecretStr 的 Responses Client。"""

    def __init__(
        self,
        api_key: SecretStr,
        transport: ResponsesTransport,
        endpoint: str = "https://api.openai.com/v1/responses",
    ) -> None:
        """保存 SecretStr、注入传输和固定端点。"""
        self._api_key = api_key
        self._transport = transport
        self._endpoint = endpoint

    def __repr__(self) -> str:
        """始终隐藏 SecretStr。"""
        return "OpenAIResponsesClient(api_key=**********)"

    def create(self, call: OpenAIResponsesCall) -> OpenAIResponsesTurn:
        """执行一次请求；错误不回显响应正文。"""
        response = self._transport.post_json(
            self._endpoint,
            {
                "authorization": f"Bearer {self._api_key.get_secret_value()}",
                "content-type": "application/json",
            },
            call.payload(),
        )
        provider_type, provider_code, provider_param = _provider_diagnostics(response.body)
        if response.status_code == HTTP_RATE_LIMIT:
            raise OpenAIResponsesError(
                OpenAIResponsesErrorKind.RATE_LIMIT,
                HTTP_RATE_LIMIT,
                provider_type,
                provider_code,
                provider_param,
            )
        if response.status_code in HTTP_TIMEOUTS:
            raise OpenAIResponsesError(
                OpenAIResponsesErrorKind.TIMEOUT,
                response.status_code,
                provider_type,
                provider_code,
                provider_param,
            )
        if not HTTP_SUCCESS_MIN <= response.status_code < HTTP_SUCCESS_MAX:
            raise OpenAIResponsesError(
                OpenAIResponsesErrorKind.PROVIDER_ERROR,
                response.status_code,
                provider_type,
                provider_code,
                provider_param,
            )
        try:
            parsed = ApiResponse.model_validate(response.body)
        except ValidationError as error:
            raise OpenAIResponsesSchemaError from error
        reasoning = parsed.usage.output_tokens_details.reasoning_tokens
        content = tuple(
            part for item in parsed.output if isinstance(item, ApiMessage) for part in item.content
        )
        return OpenAIResponsesTurn(
            response_id=parsed.id,
            model_revision=parsed.model,
            status=parsed.status,
            function_calls=tuple(
                item for item in parsed.output if isinstance(item, ApiFunctionCall)
            ),
            continuation_items=tuple(
                item.model_dump(mode="json", exclude_none=True) for item in parsed.output
            ),
            output_text="\n".join(item.text for item in content if isinstance(item, ApiOutputText)),
            refusal=any(isinstance(item, ApiRefusal) for item in content),
            token_usage=TokenUsage(
                input_tokens=parsed.usage.input_tokens,
                cached_input_tokens=parsed.usage.input_tokens_details.cached_tokens,
                output_tokens=parsed.usage.output_tokens - reasoning,
                reasoning_tokens=reasoning,
                cache_write_tokens=parsed.usage.input_tokens_details.cache_write_tokens,
            ),
            latency_ms=response.latency_ms,
        )


def _provider_diagnostics(body: JsonObject) -> tuple[str | None, str | None, str | None]:
    """仅提取错误对象中的白名单 token，明确丢弃 message。"""
    error = body.get("error")
    if not isinstance(error, dict):
        return None, None, None
    return (
        _safe_diagnostic_token(error.get("type")),
        _safe_diagnostic_token(error.get("code")),
        _safe_diagnostic_token(error.get("param")),
    )


def _safe_diagnostic_token(value: object) -> str | None:
    if isinstance(value, str) and _SAFE_DIAGNOSTIC_TOKEN.fullmatch(value) is not None:
        return value
    return None
