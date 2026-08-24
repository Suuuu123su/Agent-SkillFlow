"""图构建期的去重累加器。"""

from typing import TypeVar

from skillflow.graph.errors import GraphBuildError
from skillflow.graph.models import (
    GraphBuildData,
    GraphNodeRef,
    ProvenanceEdge,
    RevocationFact,
    SecurityEdge,
    SecurityNode,
    node_ref,
)

EdgeValue = TypeVar("EdgeValue", ProvenanceEdge, SecurityEdge)


class GraphAssembler:
    """构建期间维护可变索引，完成后只返回冻结值对象。"""

    def __init__(self, run_id: str) -> None:
        """初始化仅在构建期可变的去重索引。"""
        self._run_id = run_id
        self._nodes: dict[GraphNodeRef, SecurityNode] = {}
        self._provenance: dict[tuple[GraphNodeRef, GraphNodeRef], ProvenanceEdge] = {}
        self._security: dict[tuple[GraphNodeRef, GraphNodeRef], SecurityEdge] = {}
        self._revocations: list[RevocationFact] = []

    def add_node(self, node: SecurityNode) -> GraphNodeRef:
        """加入类型化节点，拒绝同类型同 ID 的冲突属性。"""
        reference = node_ref(node)
        existing = self._nodes.get(reference)
        if existing is not None and existing != node:
            raise GraphBuildError(reference.node_id, "同一节点具有冲突属性")
        self._nodes[reference] = node
        return reference

    def add_provenance_edge(self, edge: ProvenanceEdge) -> None:
        """加入唯一二部边。"""
        self._put_edge(self._provenance, edge)

    def add_security_edge(self, edge: SecurityEdge) -> None:
        """加入唯一语义边。"""
        self._put_edge(self._security, edge)

    def add_revocation(self, fact: RevocationFact) -> None:
        """记录不改写历史节点的事件时间撤销事实。"""
        self._revocations.append(fact)

    def finish(self) -> GraphBuildData:
        """按类型和 ID 排序，产生确定的只读构建结果。"""
        return GraphBuildData(
            run_id=self._run_id,
            nodes=tuple(sorted(self._nodes.values(), key=_node_key)),
            provenance_edges=tuple(sorted(self._provenance.values(), key=_edge_key)),
            security_edges=tuple(sorted(self._security.values(), key=_edge_key)),
            revocations=tuple(
                sorted(
                    self._revocations,
                    key=lambda fact: (fact.timestamp, fact.event_id, fact.target.node_id),
                )
            ),
        )

    @staticmethod
    def _put_edge(
        target: dict[tuple[GraphNodeRef, GraphNodeRef], EdgeValue],
        edge: EdgeValue,
    ) -> None:
        key = (edge.source, edge.target)
        existing = target.get(key)
        if existing is not None and existing != edge:
            raise GraphBuildError(
                edge.source.node_id,
                f"到 {edge.target.node_id} 的边发生冲突",
            )
        target[key] = edge


def _node_key(node: SecurityNode) -> tuple[str, str]:
    reference = node_ref(node)
    return reference.kind.value, reference.node_id


def _edge_key(edge: ProvenanceEdge | SecurityEdge) -> tuple[str, str, str, str]:
    return (
        edge.source.kind.value,
        edge.source.node_id,
        edge.target.kind.value,
        edge.target.node_id,
    )
