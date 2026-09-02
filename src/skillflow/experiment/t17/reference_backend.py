"""让模型只选择预注册动作的 Reference Harness 后端。"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Protocol

from skillflow.benchmark.scripted_backend import (
    FixtureScript,
    ScriptedBackend,
    ScriptedInputArtifact,
    ScriptedInvocation,
    ScriptedInvocationResult,
)
from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.references import FixtureImplementationRef


class ReferenceModelDecision(StrictModel):
    """模型唯一可提交的动作选择与普通任务输出。"""

    selected_action_ids: tuple[NonEmptyStr, ...]
    output_text: str
    output_mime_type: NonEmptyStr = "text/plain"


@dataclass(frozen=True, slots=True)
class ReferenceModelRequest:
    """模型可见的输入内容与封闭动作目录。"""

    implementation: FixtureImplementationRef
    inputs: tuple[ScriptedInputArtifact, ...]
    allowed_action_ids: tuple[str, ...]
    scenario_id: str
    task_prompt: str
    expected_output_text: str


@dataclass(frozen=True, slots=True)
class ReferenceRunContext:
    """一个 Run 中不会被模型修改的场景与任务输入。"""

    scenario_id: str
    task_prompt: str


DEFAULT_REFERENCE_CONTEXT: Final = ReferenceRunContext(
    "unbound",
    "执行预注册任务。",
)


class ReferenceModelClient(Protocol):
    """Fake 与真实 Responses Client 共享的决策接口。"""

    def decide(self, request: ReferenceModelRequest) -> ReferenceModelDecision:
        """选择零到多个预注册动作并返回普通任务输出。"""
        ...


class ReferenceDecisionError(ValueError):
    """模型选择了重复或未预注册动作。"""

    __slots__ = ("action_id", "implementation", "reason")

    def __init__(
        self,
        implementation: str,
        action_id: str,
        reason: str,
    ) -> None:
        """保存封闭动作身份和 reason code。"""
        super().__init__(implementation, action_id, reason)
        self.implementation = implementation
        self.action_id = action_id
        self.reason = reason

    def __str__(self) -> str:
        """返回不包含模型正文的稳定诊断。"""
        return f"{self.implementation}:{self.action_id}:{self.reason}"


class FakeReferenceModelClient:
    """无 I/O 的固定 Reference Model 决策表。"""

    def __init__(self, decisions: Mapping[str, ReferenceModelDecision]) -> None:
        """复制固定决策，隔离调用方后续修改。"""
        self._decisions = dict(decisions)

    def decide(self, request: ReferenceModelRequest) -> ReferenceModelDecision:
        """按 fixture implementation 返回固定决策。"""
        try:
            return self._decisions[request.implementation.root]
        except KeyError as error:
            raise ReferenceDecisionError(
                request.implementation.root,
                "",
                "decision_missing",
            ) from error


class ReferenceModelBackend:
    """把模型选择投影到受信 FixtureScript 动作模板。"""

    def __init__(
        self,
        scripts: Mapping[str, FixtureScript],
        client: ReferenceModelClient,
        context: ReferenceRunContext = DEFAULT_REFERENCE_CONTEXT,
    ) -> None:
        """复制预注册脚本并绑定模型决策边界。"""
        self._scripts = dict(scripts)
        self._client = client
        self._context = context

    def invoke(self, invocation: ScriptedInvocation) -> ScriptedInvocationResult:
        """只执行模型从当前脚本中选择的 action_id。"""
        root = invocation.implementation.root
        try:
            script = self._scripts[root]
        except KeyError as error:
            raise ReferenceDecisionError(root, "", "script_missing") from error
        allowed = {item.action_id: item for item in script.actions}
        decision = self._client.decide(
            ReferenceModelRequest(
                implementation=invocation.implementation,
                inputs=invocation.inputs,
                allowed_action_ids=tuple(allowed),
                scenario_id=self._context.scenario_id,
                task_prompt=self._context.task_prompt,
                expected_output_text=script.output.decode(),
            )
        )
        if len(decision.selected_action_ids) != len(set(decision.selected_action_ids)):
            raise ReferenceDecisionError(root, "", "duplicate_action")
        selected = []
        for action_id in decision.selected_action_ids:
            action = allowed.get(action_id)
            if action is None:
                raise ReferenceDecisionError(root, action_id, "action_not_registered")
            selected.append(action)
        filtered = FixtureScript(
            output=decision.output_text.encode(),
            actions=tuple(selected),
            output_mime_type=decision.output_mime_type,
        )
        return ScriptedBackend({root: filtered}).invoke(invocation)
