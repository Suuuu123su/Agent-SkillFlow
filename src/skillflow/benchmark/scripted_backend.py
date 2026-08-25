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
from skillflow.instrumentation.tool_types import (
    HttpSendArgs,
    ReadFileArgs,
    ReadMemoryArgs,
    ShellExecArgs,
    ToolActionAttempt,
    ToolArguments,
    ToolCallRequest,
    WriteMemoryArgs,
)
from skillflow.models.references import FixtureImplementationRef
from skillflow.runtime.session import ActorCall


@dataclass(frozen=True, slots=True)
class ToolScriptAction:
    """一个声明式 Mock Tool 动作。"""

    action_id: str
    decision_key: str
    arguments: ToolArguments
    input_binding: "InputArtifactBinding | None" = None
    input_gate: "InputArtifactGate | None" = None


@dataclass(frozen=True, slots=True)
class InputArtifactBinding:
    """把一个 Tool 参数的 source Artifact 绑定到调用输入。"""

    input_index: int


@dataclass(frozen=True, slots=True)
class InputArtifactGate:
    """按调用输入内容哈希选择结构基线决策键。"""

    input_index: int
    expected_content_hash: str
    mismatch_decision_key: str


@dataclass(frozen=True, slots=True)
class FixtureScript:
    """一个固定 fixture 的动作与返回值。"""

    output: bytes
    actions: tuple[ToolScriptAction, ...] = ()
    output_mime_type: str = "text/plain"


@dataclass(frozen=True, slots=True)
class ScriptedInvocationResult:
    """脚本的确定性输出、Receipt 与数据父节点。"""

    output: bytes
    receipts: tuple[ToolReceipt, ...]
    attempts: tuple[ToolActionAttempt, ...]
    parent_artifact_ids: tuple[str, ...]
    output_mime_type: str


@dataclass(frozen=True, slots=True)
class ScriptedInputArtifact:
    """Backend 可见的脱敏输入 Artifact 事实。"""

    artifact_id: str
    content_hash: str
    content_length: int


@dataclass(frozen=True, slots=True)
class ScriptedInvocation:
    """一次 Scripted Backend 调用的完整类型化输入。"""

    implementation: FixtureImplementationRef
    actor: ActorCall
    tool: InstrumentedTool
    inputs: tuple[ScriptedInputArtifact, ...] = ()


class ScriptedBackend:
    """仅从白名单 registry 读取声明式脚本。"""

    def __init__(self, scripts: Mapping[str, FixtureScript]) -> None:
        """复制受信 fixture registry，禁止运行中注入新实现。"""
        self._scripts = dict(scripts)

    def invoke(self, invocation: ScriptedInvocation) -> ScriptedInvocationResult:
        """顺序解释注册脚本，不导入模块或执行任意代码。"""
        try:
            script = self._scripts[invocation.implementation.root]
        except KeyError as error:
            raise FixtureNotFoundError(invocation.implementation.root) from error
        actor = invocation.actor
        if actor.call_id is None:
            operation = "invoke scripted backend"
            state = "call_id missing"
            raise HarnessStateError(operation, state)
        receipts: list[ToolReceipt] = []
        attempts: list[ToolActionAttempt] = []
        parent_ids: list[str] = []
        for action in script.actions:
            arguments = _bind_arguments(action, invocation.inputs)
            outcome = invocation.tool.call(
                ToolCallRequest(
                    actor_id=actor.actor_id,
                    call_id=actor.call_id,
                    action_id=action.action_id,
                    decision_key=_decision_key(action, invocation.inputs),
                    arguments=arguments,
                )
            )
            match outcome:
                case ExecutedToolCall(
                    pending=pending,
                    receipt=receipt,
                    output_artifact_ids=output_artifact_ids,
                ):
                    attempts.append(
                        ToolActionAttempt(
                            action_id=action.action_id,
                            actor_id=actor.actor_id,
                            call_id=actor.call_id,
                            tool=arguments.kind,
                            argument_artifact_id=pending.argument_artifact_id,
                            executed=True,
                        )
                    )
                    receipts.append(receipt)
                    parent_ids.extend(output_artifact_ids)
                case DeniedToolCall(pending=pending):
                    attempts.append(
                        ToolActionAttempt(
                            action_id=action.action_id,
                            actor_id=actor.actor_id,
                            call_id=actor.call_id,
                            tool=arguments.kind,
                            argument_artifact_id=pending.argument_artifact_id,
                            executed=False,
                        )
                    )
                case _ as unreachable:
                    assert_never(unreachable)
        return ScriptedInvocationResult(
            output=script.output,
            receipts=tuple(receipts),
            attempts=tuple(attempts),
            parent_artifact_ids=tuple(parent_ids),
            output_mime_type=script.output_mime_type,
        )


def _input_at(
    inputs: tuple[ScriptedInputArtifact, ...],
    index: int,
    action_id: str,
) -> ScriptedInputArtifact:
    try:
        return inputs[index]
    except IndexError as error:
        raise HarnessStateError(action_id, f"input index out of range: {index}") from error


def _decision_key(
    action: ToolScriptAction,
    inputs: tuple[ScriptedInputArtifact, ...],
) -> str:
    gate = action.input_gate
    if gate is None:
        return action.decision_key
    input_artifact = _input_at(inputs, gate.input_index, action.action_id)
    if input_artifact.content_hash == gate.expected_content_hash:
        return action.decision_key
    return gate.mismatch_decision_key


def _bind_arguments(
    action: ToolScriptAction,
    inputs: tuple[ScriptedInputArtifact, ...],
) -> ToolArguments:
    binding = action.input_binding
    if binding is None:
        return action.arguments
    artifact_id = _input_at(inputs, binding.input_index, action.action_id).artifact_id
    match action.arguments:
        case HttpSendArgs(source=source, sink=sink, sensitivity=sensitivity):
            return HttpSendArgs(
                source_artifact_id=artifact_id,
                source=source,
                sink=sink,
                sensitivity=sensitivity,
            )
        case WriteMemoryArgs(key=key, source=source, sensitivity=sensitivity):
            return WriteMemoryArgs(
                key=key,
                source_artifact_id=artifact_id,
                source=source,
                sensitivity=sensitivity,
            )
        case ReadFileArgs() | ReadMemoryArgs() | ShellExecArgs():
            raise HarnessStateError(action.action_id, "tool arguments have no artifact source")
        case _ as unreachable:
            assert_never(unreachable)
