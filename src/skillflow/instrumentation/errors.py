"""T05 Harness 与插桩边界的结构化错误。"""

from dataclasses import dataclass


class InstrumentationError(Exception):
    """T05 运行时错误基类。"""


@dataclass(frozen=True, slots=True)
class ArtifactContentError(InstrumentationError):
    """Artifact 元数据或 Blob 内容不可读取。"""

    artifact_id: str
    reason: str

    def __str__(self) -> str:
        """渲染稳定中文错误。"""
        return f"Artifact 内容不可用：{self.artifact_id}（{self.reason}）"


@dataclass(frozen=True, slots=True)
class DecisionFixtureError(InstrumentationError):
    """Stub 决策 fixture 缺失或包含非法结果。"""

    key: str
    reason: str

    def __str__(self) -> str:
        """渲染稳定中文错误。"""
        return f"决策 fixture 无效：{self.key}（{self.reason}）"


@dataclass(frozen=True, slots=True)
class FixtureNotFoundError(InstrumentationError):
    """Scripted Backend 没有注册请求的 fixture。"""

    reference: str

    def __str__(self) -> str:
        """渲染稳定中文错误。"""
        return f"fixture 未注册：{self.reference}"


@dataclass(slots=True)
class HarnessStateError(InstrumentationError):
    """Harness 操作与当前 Session 状态不相容。"""

    operation: str
    state: str

    def __str__(self) -> str:
        """渲染稳定中文错误。"""
        return f"Harness 状态不允许 {self.operation}：{self.state}"


@dataclass(frozen=True, slots=True)
class MemoryKeyMissingError(InstrumentationError):
    """读取或删除不存在的 Memory key。"""

    key: str

    def __str__(self) -> str:
        """渲染稳定中文错误。"""
        return f"Memory key 不存在：{self.key}"


@dataclass(frozen=True, slots=True)
class ReceiptAuthorityError(InstrumentationError):
    """非 Mock Tool Adapter 尝试创建 Receipt。"""

    def __str__(self) -> str:
        """渲染稳定中文错误。"""
        return "Tool Receipt 只能由 Mock Tool Adapter 创建"


@dataclass(frozen=True, slots=True)
class SkillLifecycleError(InstrumentationError):
    """Skill 生命周期转换非法。"""

    skill_id: str
    operation: str
    state: str

    def __str__(self) -> str:
        """渲染稳定中文错误。"""
        return f"Skill {self.skill_id} 无法执行 {self.operation}：当前状态 {self.state}"


@dataclass(frozen=True, slots=True)
class UnsupportedStepError(InstrumentationError):
    """T05 无法安全解释某个 Scenario 步骤。"""

    step_id: str
    action: str

    def __str__(self) -> str:
        """渲染稳定中文错误。"""
        return f"T05 不支持步骤 {self.step_id}：{self.action}"


@dataclass(frozen=True, slots=True)
class WorkspaceEscapeError(InstrumentationError):
    """资源规范化后逃出固定 Workspace 根。"""

    resource: str

    def __str__(self) -> str:
        """渲染稳定中文错误。"""
        return f"Workspace 路径逃逸被拒绝：{self.resource}"


@dataclass(frozen=True, slots=True)
class WorkspaceResourceError(InstrumentationError):
    """文件代理收到非 Workspace 资源或文件访问失败。"""

    resource: str
    reason: str

    def __str__(self) -> str:
        """渲染稳定中文错误。"""
        return f"Workspace 资源不可用：{self.resource}（{self.reason}）"
