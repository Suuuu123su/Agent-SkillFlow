"""先保存成功响应的用量，再解析模型输出；正文仅留在本地私有记录。"""

import json
import os
import time
from collections.abc import Mapping
from pathlib import Path

from pydantic import Field, SecretStr, ValidationError

from skillflow.experiment.t16.openai_response_models import (
    ApiModel,
    ApiUsage,
    JsonObject,
    OpenAIResponsesCall,
)
from skillflow.experiment.t16.openai_responses import (
    HTTP_SUCCESS_MAX,
    HTTP_SUCCESS_MIN,
    OpenAIResponsesClient,
    OpenAIResponsesError,
    OpenAIResponsesSchemaError,
    OpenAIResponsesTurn,
    ResponsesTransport,
    TransportResponse,
)
from skillflow.experiment.t16.provider import TokenUsage, estimate_result_cost
from skillflow.experiment.t17.v2.api_models import (
    V2ProviderFailureError,
    V2UsageUnavailableError,
    V2UsageWriteFailureError,
)
from skillflow.experiment.t17.v2.journal import V2UsageJournal


class ResponseHeader(ApiModel):
    """即使输出结构错误，仍能独立验证用量和提供方身份。"""

    id: str = Field(min_length=1, max_length=256, pattern=r"^[A-Za-z0-9_-]+$")
    model: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._-]+$")
    status: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    usage: ApiUsage


class AuditedResponsesTransport:
    """网络层不持有授权逻辑；所有请求都必须先有已同步的尝试记录。"""

    def __init__(
        self, transport: ResponsesTransport, journal: V2UsageJournal, secret: SecretStr
    ) -> None:
        """仅在内存中持有凭据，以阻止响应偶然回显真实密钥到本地。"""
        self._transport, self._journal, self._secret = transport, journal, secret

    def post_json(
        self, url: str, headers: Mapping[str, str], payload: JsonObject
    ) -> TransportResponse:
        """一次请求只写一次用量；不保存 HTTP 错误正文或请求头。"""
        journal = self._journal
        if (
            url != journal.config.endpoint
            or not journal.events
            or journal.events[-1].event_type != "attempt"
        ):
            raise V2UsageWriteFailureError("v2_unjournaled_or_wrong_endpoint_request")
        started = time.perf_counter()
        try:
            response = self._transport.post_json(url, headers, payload)
        except OpenAIResponsesError as error:
            journal.append(
                "transport_failure",
                reason=error.kind.value,
                latency_ms=max(0, round((time.perf_counter() - started) * 1000)),
            )
            raise
        except (V2ProviderFailureError, V2UsageUnavailableError) as error:
            reason = (
                "usage_unavailable"
                if isinstance(error, V2UsageUnavailableError)
                else "network_response_state_unknown"
            )
            journal.append(
                "transport_failure",
                reason=reason,
                latency_ms=max(0, round((time.perf_counter() - started) * 1000)),
            )
            raise
        if not HTTP_SUCCESS_MIN <= response.status_code < HTTP_SUCCESS_MAX:
            journal.append(
                "http_error",
                reason=f"http_status_{response.status_code}",
                latency_ms=response.latency_ms,
            )
            return response
        try:
            header = ResponseHeader.model_validate(response.body)
            usage = _token_usage(header.usage)
        except (ValueError, ValidationError) as error:
            journal.append(
                "transport_failure", reason="usage_unavailable", latency_ms=response.latency_ms
            )
            raise V2UsageUnavailableError("v2_response_usage_unavailable") from error
        journal.received = journal.append(
            "response",
            usage=usage,
            response_id=header.id,
            model_revision=header.model,
            response_status=header.status,
            latency_ms=response.latency_ms,
            estimated_cost_usd=estimate_result_cost(journal.config.provider.pricing, usage),
        )
        _write_private_response(
            journal.path.parent / "api-private" / f"{journal.attempt_index:06d}.json",
            payload,
            response.body,
            self._secret,
        )
        return response


class UsagePreservingClient:
    """格式错误保留真实用量，但返回明确错误状态而非伪造成功。"""

    def __init__(self, client: OpenAIResponsesClient, journal: V2UsageJournal) -> None:
        """包装现有解析器，保持 T16 和旧 T17 行为不变。"""
        self._client, self._journal = client, journal

    def create(self, call: OpenAIResponsesCall) -> OpenAIResponsesTurn:
        """输出格式失败也要经过同一费用结算路径，不能重采样。"""
        try:
            return self._client.create(call)
        except OpenAIResponsesSchemaError as error:
            event = self._journal.received
            if (
                event is None
                or event.usage is None
                or event.response_id is None
                or event.model_revision is None
                or event.latency_ms is None
            ):
                raise V2UsageUnavailableError("v2_schema_failure_without_usage") from error
            return OpenAIResponsesTurn(
                response_id=event.response_id,
                model_revision=event.model_revision,
                status="schema_rejection",
                function_calls=(),
                continuation_items=(),
                output_text="",
                refusal=False,
                token_usage=event.usage,
                latency_ms=event.latency_ms,
            )


def _token_usage(usage: ApiUsage) -> TokenUsage:
    if usage.total_tokens != usage.input_tokens + usage.output_tokens:
        raise ValueError("v2_usage_total_mismatch")
    reasoning = usage.output_tokens_details.reasoning_tokens
    return TokenUsage(
        input_tokens=usage.input_tokens,
        cached_input_tokens=usage.input_tokens_details.cached_tokens,
        cache_write_tokens=usage.input_tokens_details.cache_write_tokens,
        output_tokens=usage.output_tokens - reasoning,
        reasoning_tokens=reasoning,
    )


def _write_private_response(
    path: Path, request: JsonObject, response: JsonObject, secret: SecretStr
) -> None:
    text = json.dumps(
        {"request": request, "response": response}, ensure_ascii=False, sort_keys=True
    )
    key = secret.get_secret_value()
    if key:
        text = text.replace(key, "[REDACTED_CREDENTIAL]")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(text + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as error:
        raise V2UsageWriteFailureError("v2_private_response_write_failed") from error
