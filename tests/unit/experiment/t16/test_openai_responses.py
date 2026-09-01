import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field

import pytest
from pydantic import JsonValue, SecretStr

from skillflow.experiment.t16.openai_output_schemas import ResponseOutputContract
from skillflow.experiment.t16.openai_responses import (
    OpenAIResponsesCall,
    OpenAIResponsesClient,
    OpenAIResponsesError,
    OpenAIResponsesErrorKind,
    OpenAIResponsesSchemaError,
    ResponsesTransport,
    TransportResponse,
)
from skillflow.experiment.t16.provider import ReasoningEffort


def _response() -> dict[str, JsonValue]:
    return {
        "id": "resp_test_1",
        "model": "gpt-5.6-luna",
        "status": "completed",
        "output": [
            {
                "id": "rs_test_1",
                "type": "reasoning",
                "summary": [],
                "encrypted_content": "opaque-reasoning",
                "status": "completed",
            },
            {
                "id": "fc_test_1",
                "type": "function_call",
                "call_id": "call_test_1",
                "name": "skillflow_safe_effect",
                "arguments": '{"effect_alias":"context-harm"}',
                "status": "completed",
            },
        ],
        "usage": {
            "input_tokens": 100,
            "input_tokens_details": {"cached_tokens": 20, "cache_write_tokens": 4},
            "output_tokens": 30,
            "output_tokens_details": {"reasoning_tokens": 10},
            "total_tokens": 130,
        },
    }


@dataclass
class RecordingTransport(ResponsesTransport):
    response: TransportResponse
    urls: list[str] = field(default_factory=list)
    headers: list[Mapping[str, str]] = field(default_factory=list)
    payloads: list[dict[str, JsonValue]] = field(default_factory=list)

    def post_json(
        self,
        url: str,
        headers: Mapping[str, str],
        payload: dict[str, JsonValue],
    ) -> TransportResponse:
        self.urls.append(url)
        self.headers.append(headers)
        self.payloads.append(payload)
        return self.response


def _call() -> OpenAIResponsesCall:
    return OpenAIResponsesCall(
        model="gpt-5.6-luna",
        temperature=0.2,
        reasoning_effort=ReasoningEffort.MEDIUM,
        max_output_tokens=512,
        input_items=(
            {
                "role": "user",
                "content": [{"type": "input_text", "text": "处理隔离任务"}],
            },
        ),
        tools=(
            {
                "type": "function",
                "name": "skillflow_safe_effect",
                "description": "只写入本地安全收据",
                "strict": True,
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {"effect_alias": {"type": "string"}},
                    "required": ["effect_alias"],
                },
            },
        ),
    )


def test_client_sends_stateless_bounded_request_and_splits_reasoning_usage() -> None:
    transport = RecordingTransport(TransportResponse(200, _response(), 37))
    marker_text = str(uuid.UUID(int=67890))
    client = OpenAIResponsesClient(SecretStr(marker_text), transport)

    turn = client.create(_call())

    payload = transport.payloads[0]
    assert payload["model"] == "gpt-5.6-luna"
    assert payload["store"] is False
    assert payload["parallel_tool_calls"] is False
    assert payload["prompt_cache_options"] == {"mode": "explicit"}
    assert payload["include"] == ["reasoning.encrypted_content"]
    assert marker_text not in str(payload)
    assert transport.headers[0]["authorization"] == f"Bearer {marker_text}"
    assert marker_text not in repr(client)
    assert turn.response_id == "resp_test_1"
    assert turn.model_revision == "gpt-5.6-luna"
    assert turn.token_usage.input_tokens == 100
    assert turn.token_usage.cached_input_tokens == 20
    assert turn.token_usage.cache_write_tokens == 4
    assert turn.token_usage.output_tokens == 20
    assert turn.token_usage.reasoning_tokens == 10
    assert turn.function_calls[0].call_id == "call_test_1"
    assert turn.latency_ms == 37


def test_request_omits_temperature_when_reasoning_model_does_not_support_it() -> None:
    transport = RecordingTransport(TransportResponse(200, _response(), 1))
    call = _call().model_copy(update={"temperature": None})

    OpenAIResponsesClient(SecretStr("masked"), transport).create(call)

    assert "temperature" not in transport.payloads[0]


def test_v3_task_result_contract_replaces_legacy_finish_schema() -> None:
    call = _call().model_copy(update={"output_contract": ResponseOutputContract.TASK_RESULT_V3})

    schema = call.payload()["text"]["format"]

    assert schema["name"] == "skillflow_task_result_v3"
    assert schema["schema"]["required"] == [
        "schema_version",
        "task_status",
        "result_kind",
        "fact_ids",
        "value_id",
    ]
    assert set(schema["schema"]["properties"]) == set(schema["schema"]["required"])


def test_rate_limit_error_never_includes_response_body_or_secret() -> None:
    marker_text = str(uuid.UUID(int=98765))
    transport = RecordingTransport(
        TransportResponse(429, {"error": {"message": marker_text, "type": "rate_limit"}}, 5)
    )

    with pytest.raises(OpenAIResponsesError) as captured:
        OpenAIResponsesClient(SecretStr(marker_text), transport).create(_call())

    assert captured.value.kind is OpenAIResponsesErrorKind.RATE_LIMIT
    assert marker_text not in str(captured.value)
    assert "rate_limit" in str(captured.value)


def test_provider_error_keeps_only_whitelisted_diagnostics() -> None:
    marker_text = str(uuid.UUID(int=24680))
    transport = RecordingTransport(
        TransportResponse(
            400,
            {
                "error": {
                    "message": marker_text,
                    "type": "invalid_request_error",
                    "code": "unsupported_parameter",
                    "param": "temperature",
                }
            },
            5,
        )
    )

    with pytest.raises(OpenAIResponsesError) as captured:
        OpenAIResponsesClient(SecretStr(marker_text), transport).create(_call())

    error = captured.value
    assert error.status_code == 400
    assert error.provider_type == "invalid_request_error"
    assert error.provider_code == "unsupported_parameter"
    assert error.provider_param == "temperature"
    assert marker_text not in str(error)


def test_unknown_output_item_is_a_schema_error() -> None:
    response = _response()
    output = response["output"]
    assert isinstance(output, list)
    output.append({"id": "unknown", "type": "web_search_call"})
    transport = RecordingTransport(TransportResponse(200, response, 1))

    with pytest.raises(OpenAIResponsesSchemaError):
        OpenAIResponsesClient(SecretStr("masked"), transport).create(_call())


def test_missing_usage_is_a_schema_error_not_zero_cost() -> None:
    response = _response()
    del response["usage"]
    transport = RecordingTransport(TransportResponse(200, response, 1))

    with pytest.raises(OpenAIResponsesSchemaError):
        OpenAIResponsesClient(SecretStr("masked"), transport).create(_call())


@pytest.mark.parametrize("missing_field", ["input_tokens_details", "output_tokens_details"])
def test_missing_usage_breakdown_is_a_schema_error_not_zero(
    missing_field: str,
) -> None:
    response = _response()
    usage = response["usage"]
    assert isinstance(usage, dict)
    del usage[missing_field]
    transport = RecordingTransport(TransportResponse(200, response, 1))

    with pytest.raises(OpenAIResponsesSchemaError):
        OpenAIResponsesClient(SecretStr("masked"), transport).create(_call())
