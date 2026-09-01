"""Responses Tool 调用的本地执行、审计与可恢复错误回传。"""

from dataclasses import dataclass
from typing import Literal

from skillflow.experiment.t16.live_records import LiveToolCallAudit
from skillflow.experiment.t16.live_tools import (
    LiveToolLookupError,
    LiveToolRuntime,
    LiveToolSchemaError,
    UnknownEffectAliasError,
)
from skillflow.experiment.t16.openai_response_models import (
    ApiFunctionCall,
    JsonObject,
)
from skillflow.experiment.t16.openai_responses import OpenAIResponsesTurn


@dataclass(frozen=True, slots=True)
class _RecoverableToolFailure:
    """可回传模型且不会丢失目标别名的 Tool 失败。"""

    reason: Literal["lookup_error", "unknown_effect_alias"]
    effect_alias: str | None = None


@dataclass(frozen=True, slots=True)
class ToolLoopContext:
    """一轮 Tool 执行共享的 Session、Runtime 与审计容器。"""

    session_index: int
    runtime: LiveToolRuntime
    history: list[JsonObject]
    audits: list[LiveToolCallAudit]


def execute_tools(
    turn: OpenAIResponsesTurn,
    context: ToolLoopContext,
) -> bool:
    """执行一轮 Tool calls；任何结构拒绝返回 true。"""
    context.history.extend(turn.continuation_items)
    for function_call in turn.function_calls:
        try:
            result = context.runtime.execute(function_call.name, function_call.arguments)
        except LiveToolSchemaError:
            context.audits.append(
                LiveToolCallAudit(
                    session_index=context.session_index,
                    call_id=function_call.call_id,
                    tool_name=function_call.name,
                    accepted=False,
                    rejection_reason="schema_error",
                )
            )
            return True
        except LiveToolLookupError:
            _append_recoverable_tool_error(
                function_call,
                _RecoverableToolFailure("lookup_error"),
                context,
            )
            continue
        except UnknownEffectAliasError as error:
            _append_recoverable_tool_error(
                function_call,
                _RecoverableToolFailure("unknown_effect_alias", error.effect_alias),
                context,
            )
            continue
        context.audits.append(
            LiveToolCallAudit(
                session_index=context.session_index,
                call_id=function_call.call_id,
                tool_name=function_call.name,
                accepted=True,
                effect_alias=result.effect_alias,
                receipt_id=result.receipt_id,
            )
        )
        context.history.append(
            {
                "type": "function_call_output",
                "call_id": function_call.call_id,
                "output": result.output,
            }
        )
    return False


def _append_recoverable_tool_error(
    function_call: ApiFunctionCall,
    failure: _RecoverableToolFailure,
    context: ToolLoopContext,
) -> None:
    """把可恢复执行错误回传模型，同时保持未执行审计。"""
    context.audits.append(
        LiveToolCallAudit(
            session_index=context.session_index,
            call_id=function_call.call_id,
            tool_name=function_call.name,
            accepted=False,
            rejection_reason=failure.reason,
            effect_alias=failure.effect_alias,
        )
    )
    context.history.append(
        {
            "type": "function_call_output",
            "call_id": function_call.call_id,
            "output": f'{{"ok":false,"error":"{failure.reason}"}}',
        }
    )
