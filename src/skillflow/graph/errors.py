"""T07 图构建、查询与导出的类型化错误。"""

from dataclasses import dataclass
from pathlib import Path

from skillflow.graph.enums import GraphNodeKind


@dataclass(frozen=True, slots=True)
class GraphBuildError(Exception):
    """EventStore 事实无法形成一致图时抛出。"""

    event_id: str
    reason: str

    def __str__(self) -> str:
        """返回包含事实 ID 的诊断。"""
        return f"图事实 {self.event_id} 无效：{self.reason}"


@dataclass(frozen=True, slots=True)
class GraphNodeNotFoundError(Exception):
    """查询 ID 在当前 Run 中不存在。"""

    node_id: str

    def __str__(self) -> str:
        """返回缺失节点 ID。"""
        return f"图节点不存在：{self.node_id}"


@dataclass(frozen=True, slots=True)
class GraphNodeAmbiguousError(Exception):
    """同一原始 ID 对应多个节点类型。"""

    node_id: str

    def __str__(self) -> str:
        """返回发生冲突的原始 ID。"""
        return f"图节点 ID 在多个类型中冲突：{self.node_id}"


@dataclass(frozen=True, slots=True)
class GraphNodeKindError(Exception):
    """专用查询收到错误类型的节点。"""

    node_id: str
    expected: GraphNodeKind
    actual: GraphNodeKind

    def __str__(self) -> str:
        """返回期望与实际节点类型。"""
        return f"图节点 {self.node_id} 类型为 {self.actual}，要求 {self.expected}"


@dataclass(frozen=True, slots=True)
class GraphRunMismatchError(Exception):
    """跨会话查询使用了另一个 Run ID。"""

    expected: str
    actual: str

    def __str__(self) -> str:
        """返回期望和实际 Run ID。"""
        return f"图仅包含 Run {self.expected}，不能查询 {self.actual}"


@dataclass(frozen=True, slots=True)
class GraphQueryLimitError(Exception):
    """路径深度上限不是正整数。"""

    max_depth: int

    def __str__(self) -> str:
        """返回非法深度值。"""
        return f"max_depth 必须为正整数，实际为 {self.max_depth}"


@dataclass(frozen=True, slots=True)
class GraphExportError(Exception):
    """脱敏图 JSON 无法安全写入。"""

    path: Path
    reason: str

    def __str__(self) -> str:
        """返回导出路径与底层原因。"""
        return f"无法导出安全图 {self.path}：{self.reason}"
