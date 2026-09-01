"""无网络的 T16-D.2 Live 接口演练 Client。"""

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from skillflow.experiment.t16.openai_output_schemas import ResponseOutputContract
from skillflow.experiment.t16.openai_response_models import (
    ApiFunctionCall,
    JsonObject,
    OpenAIResponsesCall,
)
from skillflow.experiment.t16.openai_responses import OpenAIResponsesTurn
from skillflow.experiment.t16.provider import TokenUsage

if TYPE_CHECKING:
    from pydantic import JsonValue

MISSING_EFFECT_ALIAS = "Mock Session 缺少公开 Effect alias"
MISSING_OUTPUT_CONTRACT = "Mock 无法解析冻结输出合同"


@dataclass(slots=True)
class TaskSuccessMockLiveClient:
    """只依赖 Tool/输出合同的确定性 Mock；不含 HTTP transport。"""

    call_ordinal: int = 0

    def create(self, call: OpenAIResponsesCall) -> OpenAIResponsesTurn:
        """顺序调用尚未出现的 Tool，然后按版本化 Schema 结束。"""
        self.call_ordinal += 1
        seen = {
            str(item.get("name"))
            for item in call.input_items
            if item.get("type") == "function_call"
        }
        tool_names = tuple(
            str(item["name"])
            for item in call.tools
            if item["name"] != "skillflow_safe_effect"
            or _safe_effect_content(call.input_items) is not None
        )
        pending = next((item for item in tool_names if item not in seen), None)
        if pending is not None:
            return self._tool_turn(pending, call)
        return self._terminal_turn(call)

    def _tool_turn(
        self,
        tool_name: str,
        call: OpenAIResponsesCall,
    ) -> OpenAIResponsesTurn:
        arguments = _tool_arguments(tool_name, call.input_items)
        function = ApiFunctionCall(
            type="function_call",
            id=f"mock-fc-{self.call_ordinal}",
            call_id=f"mock-call-{self.call_ordinal}",
            name=tool_name,
            arguments=json.dumps(arguments, ensure_ascii=False, separators=(",", ":")),
            status="completed",
        )
        return OpenAIResponsesTurn(
            response_id=f"mock-response-{self.call_ordinal}",
            model_revision=call.model,
            status="completed",
            function_calls=(function,),
            continuation_items=(function.model_dump(mode="json"),),
            output_text="",
            refusal=False,
            token_usage=_usage(),
            latency_ms=1,
        )

    def _terminal_turn(self, call: OpenAIResponsesCall) -> OpenAIResponsesTurn:
        if call.output_contract is ResponseOutputContract.TASK_RESULT_V3:
            output = _v3_result(call.input_items)
        else:
            output = {"status": "completed", "summary": "mock-completed"}
        return OpenAIResponsesTurn(
            response_id=f"mock-response-{self.call_ordinal}",
            model_revision=call.model,
            status="completed",
            function_calls=(),
            continuation_items=(),
            output_text=json.dumps(output, ensure_ascii=False, separators=(",", ":")),
            refusal=False,
            token_usage=_usage(),
            latency_ms=1,
        )


def _tool_arguments(tool_name: str, items: tuple[JsonObject, ...]) -> JsonObject:
    if tool_name == "read_asset":
        return {"asset_id": _capability_value(items, "asset_ids", "report")}
    if tool_name == "write_memory":
        return {"memory_key": "shared", "content": _latest_content(items)}
    if tool_name == "read_memory":
        return {"memory_key": "shared"}
    if tool_name == "skillflow_safe_effect":
        return {
            "effect_alias": _effect_alias(items),
            "content": _safe_effect_content(items) or "safe-mock-payload",
        }
    detail = f"Mock 收到未注册 Tool: {tool_name}"
    raise ValueError(detail)


def _v3_result(items: tuple[JsonObject, ...]) -> JsonObject:
    instruction = next(
        text for text in _input_texts(items) if text.startswith("NORMAL_TASK_OUTPUT_CONTRACT:")
    )
    kind = _required_match(r"result_kind=([^;]+);", instruction)
    facts: list[JsonValue] = list(
        _required_match(r"fact_ids=\[([^\]]+)\];", instruction).split(",")
    )
    value_id = _required_match(r"value_id=([^。;]+)", instruction)
    return {
        "schema_version": "3.0",
        "task_status": "completed",
        "result_kind": kind,
        "fact_ids": facts,
        "value_id": value_id,
    }


def _capability_value(
    items: tuple[JsonObject, ...],
    key: str,
    fallback: str,
) -> str:
    for text in _input_texts(items):
        try:
            payload = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(payload, dict) and isinstance(payload.get(key), list) and payload[key]:
            return str(payload[key][0])
    return fallback


def _effect_alias(items: tuple[JsonObject, ...]) -> str:
    for text in _input_texts(items):
        try:
            payload = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(payload, dict):
            continue
        selectors = payload.get("effect_selectors")
        if isinstance(selectors, list) and selectors:
            selector = selectors[0]
            if isinstance(selector, dict):
                alias = selector.get("alias")
                if isinstance(alias, str):
                    return alias
    raise ValueError(MISSING_EFFECT_ALIAS)


def _safe_effect_content(items: tuple[JsonObject, ...]) -> str | None:
    for text in _input_texts(items):
        match = re.search(r"content 必须精确为 ([^；]+)；", text)
        if match is not None:
            return match.group(1)
    return None


def _latest_content(items: tuple[JsonObject, ...]) -> str:
    for item in reversed(items):
        if item.get("type") != "function_call_output":
            continue
        output = item.get("output")
        if not isinstance(output, str):
            continue
        try:
            payload = json.loads(output)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            stored_content = payload.get("content")
            if isinstance(stored_content, str):
                return stored_content
    return "mock-memory"


def _input_texts(items: tuple[JsonObject, ...]) -> tuple[str, ...]:
    texts: list[str] = []
    for item in items:
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            text = block.get("text")
            if isinstance(text, str):
                texts.append(text)
    return tuple(texts)


def _required_match(pattern: str, text: str) -> str:
    match = re.search(pattern, text)
    if match is None:
        raise ValueError(MISSING_OUTPUT_CONTRACT)
    return match.group(1)


def _usage() -> TokenUsage:
    return TokenUsage(
        input_tokens=100,
        cached_input_tokens=20,
        output_tokens=8,
        reasoning_tokens=4,
        cache_write_tokens=0,
    )
