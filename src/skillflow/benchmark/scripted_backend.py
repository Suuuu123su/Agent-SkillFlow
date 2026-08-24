"""只解释白名单动作的 Scripted Backend。"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import assert_never

from skillflow.instrumentation.errors import FixtureNotFoundError, HarnessStateError
from skillflow.instrumentation.tool_proxy import (
    DeniedToolCall,
    ExecutedToolCall,
    InstrumentedTool,
)
from skillflow.instrumentation.tool_receipt import ToolReceipt
from skillflow.instrumentation.tool_types import ToolArguments, ToolCallRequest
from skillflow.models.references import FixtureImplementationRef
from skillflow.runtime.session import ActorCall


@dataclass(frozen=True, slots=True)
class ToolScriptAction:
    """一个声明式 Mock Tool 动作。"""

    decision_key: str
    arguments: ToolArguments


@dataclass(frozen=True, slots=True)
class FixtureScript:
    """一个固定 fixture 的动作与返回值。"""

    output: bytes
    actions: tuple[ToolScriptAction, ...] = ()


@dataclass(frozen=True, slots=True)
class ScriptedInvocationResult:
    """脚本的确定性输出、Receipt 与数据父节点。"""

    output: bytes
    receipts: tuple[ToolReceipt, ...]
    parent_artifact_ids: tuple[str, ...]


class ScriptedBackend:
    """仅从白名单 registry 读取声明式脚本。"""

    def __init__(self, scripts: Mapping[str, FixtureScript]) -> None:
        """复制受信 fixture registry，禁止运行中注入新实现。"""
        self._scripts = dict(scripts)

    def invoke(
        self,
        implementation: FixtureImplementationRef,
        actor: ActorCall,
        tool: InstrumentedTool,
    ) -> ScriptedInvocationResult:
        """顺序解释注册脚本，不导入模块或执行任意代码。"""
        try:
            script = self._scripts[implementation.root]
        except KeyError as error:
            raise FixtureNotFoundError(implementation.root) from error
        if actor.call_id is None:
            operation = "invoke scripted backend"
            state = "call_id missing"
            raise HarnessStateError(operation, state)
        receipts: list[ToolReceipt] = []
        parent_ids: list[str] = []
        for action in script.actions:
            outcome = tool.call(
                ToolCallRequest(
                    actor_id=actor.actor_id,
                    call_id=actor.call_id,
                    decision_key=action.decision_key,
                    arguments=action.arguments,
                )
            )
            match outcome:
                case ExecutedToolCall(
                    receipt=receipt,
                    output_artifact_ids=output_artifact_ids,
                ):
                    receipts.append(receipt)
                    parent_ids.extend(output_artifact_ids)
                case DeniedToolCall():
                    pass
                case _ as unreachable:
                    assert_never(unreachable)
        return ScriptedInvocationResult(
            output=script.output,
            receipts=tuple(receipts),
            parent_artifact_ids=tuple(parent_ids),
        )
