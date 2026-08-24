"""Harness Adapter 的最小公开合同。"""

from dataclasses import dataclass
from typing import Protocol

from skillflow.instrumentation.tool_receipt import ToolReceipt
from skillflow.models.provenance import Artifact
from skillflow.models.references import FixtureImplementationRef


@dataclass(frozen=True, slots=True)
class HarnessSession:
    """一次 Harness Session 的稳定标识。"""

    session_id: str


@dataclass(frozen=True, slots=True)
class SkillBinding:
    """Skill 主体与白名单 fixture 实现的绑定。"""

    skill_id: str
    implementation: FixtureImplementationRef


@dataclass(frozen=True, slots=True)
class SkillInvocation:
    """一次显式 Skill 调用。"""

    skill_id: str
    input_artifact_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SkillInvocationResult:
    """Skill 返回 Artifact 及本次调用产生的 Receipt。"""

    output: Artifact
    receipts: tuple[ToolReceipt, ...]


class HarnessAdapter(Protocol):
    """T05 最小 Harness 合同，不包含 checkpoint/restore。"""

    def start_session(self, session: HarnessSession) -> None:
        """开始一个隔离 Session。"""
        ...

    def load_skill(self, binding: SkillBinding) -> None:
        """从固定 fixture registry 加载 Skill。"""
        ...

    def invoke_skill(self, invocation: SkillInvocation) -> SkillInvocationResult:
        """执行一次确定性 Skill 调用。"""
        ...

    def end_session(self) -> None:
        """结束当前 Session。"""
        ...
