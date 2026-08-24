"""带访问集合与深度上限的确定性路径物化。"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from itertools import pairwise
from typing import Final, TypeAlias

import networkx as nx

from skillflow.graph.enums import GraphNodeKind, SecurityRelation
from skillflow.graph.errors import (
    GraphNodeAmbiguousError,
    GraphNodeKindError,
    GraphNodeNotFoundError,
    GraphQueryLimitError,
)
from skillflow.graph.models import (
    GraphNodeRef,
    RevocationFact,
    SecurityEdge,
    SecurityNode,
    SecurityPath,
)
from skillflow.graph.path_analysis import (
    calculate_boundary_depth,
    group_path_nodes,
    is_auth_grant_event,
    is_untrusted_artifact,
    latest_event_time,
    ordered_session_trace,
)

DEFAULT_MAX_DEPTH: Final = 64
MAX_PATHS: Final = 512
SecurityDiGraph: TypeAlias = "nx.DiGraph[GraphNodeRef, dict[str, object], dict[str, object]]"


@dataclass(frozen=True, slots=True)
class PathRequest:
    """一次有限多源多目标路径请求。"""

    sources: tuple[GraphNodeRef, ...]
    sinks: tuple[GraphNodeRef, ...]
    max_depth: int


@dataclass(frozen=True, slots=True)
class PathContext:
    """路径查询所需的冻结图与强类型索引。"""

    graph: SecurityDiGraph
    nodes: Mapping[GraphNodeRef, SecurityNode]
    edges: Mapping[tuple[GraphNodeRef, GraphNodeRef], SecurityEdge]
    raw_index: Mapping[str, tuple[GraphNodeRef, ...]]
    revocations: Mapping[GraphNodeRef, tuple[RevocationFact, ...]]


class GraphPathFinder:
    """在冻结 SecurityGraph 上执行全部只读路径查询。"""

    def __init__(self, context: PathContext) -> None:
        """绑定只读图上下文。"""
        self._context = context

    def resolve(self, node_id: str, expected: GraphNodeKind | None = None) -> GraphNodeRef:
        """把原始 ID 解析为唯一类型化节点。"""
        candidates = self._context.raw_index.get(node_id, ())
        if not candidates:
            raise GraphNodeNotFoundError(node_id)
        if len(candidates) != 1:
            raise GraphNodeAmbiguousError(node_id)
        reference = candidates[0]
        if expected is not None and reference.kind is not expected:
            raise GraphNodeKindError(node_id, expected, reference.kind)
        return reference

    def search(self, request: PathRequest) -> tuple[SecurityPath, ...]:
        """枚举不重复节点的有限简单路径。"""
        if request.max_depth <= 0:
            raise GraphQueryLimitError(request.max_depth)
        sink_set = frozenset(request.sinks)
        found: list[tuple[GraphNodeRef, ...]] = []
        for source in sorted(request.sources, key=_ref_key):
            stack: list[
                tuple[
                    GraphNodeRef,
                    tuple[GraphNodeRef, ...],
                    frozenset[GraphNodeRef],
                ]
            ] = [(source, (source,), frozenset({source}))]
            while stack and len(found) < MAX_PATHS:
                current, path, visited = stack.pop()
                if current in sink_set and len(path) > 1:
                    found.append(path)
                    continue
                if len(path) - 1 >= request.max_depth:
                    continue
                successors = sorted(
                    self._context.graph.successors(current),
                    key=_ref_key,
                    reverse=True,
                )
                stack.extend(
                    (successor, (*path, successor), visited | {successor})
                    for successor in successors
                    if successor not in visited
                )
        unique = tuple(dict.fromkeys(found))
        return tuple(self._materialize(path) for path in sorted(unique, key=_path_key))

    def ancestors(self, artifact: GraphNodeRef, max_depth: int) -> tuple[SecurityPath, ...]:
        """返回每个可达祖先到目标 Artifact 的路径。"""
        sources = tuple(nx.ancestors(self._context.graph, artifact))
        return self.search(PathRequest(sources, (artifact,), max_depth))

    def untrusted(self, effect: GraphNodeRef, max_depth: int) -> tuple[SecurityPath, ...]:
        """只从 EventStore trust=untrusted 的 Artifact 出发。"""
        sources = tuple(
            reference
            for reference, node in self._context.nodes.items()
            if reference.kind is GraphNodeKind.ARTIFACT
            and is_untrusted_artifact(node)
            and nx.has_path(self._context.graph, reference, effect)
        )
        return self.search(PathRequest(sources, (effect,), max_depth))

    def authorization(self, effect: GraphNodeRef, max_depth: int) -> tuple[SecurityPath, ...]:
        """优先从 AUTH_GRANT Event 出发，缺失时退到关联 Grant 节点。"""
        grant_events = tuple(
            reference
            for reference, node in self._context.nodes.items()
            if reference.kind is GraphNodeKind.EVENT
            and is_auth_grant_event(node)
            and nx.has_path(self._context.graph, reference, effect)
        )
        grants = tuple(
            reference
            for reference in self._context.nodes
            if reference.kind is GraphNodeKind.GRANT
            and nx.has_path(self._context.graph, reference, effect)
        )
        sources = grant_events or grants
        return self.search(PathRequest(sources, (effect,), max_depth))

    def revoked(self, effect: GraphNodeRef, max_depth: int) -> tuple[SecurityPath, ...]:
        """返回在 Effect 时点前已撤销且仍可到达它的祖先。"""
        sources = tuple(
            reference
            for reference in self._context.revocations
            if nx.has_path(self._context.graph, reference, effect)
        )
        paths = self.search(PathRequest(sources, (effect,), max_depth))
        return tuple(path for path in paths if path.revoked_origin_ids)

    def cross_session(self, max_depth: int) -> tuple[SecurityPath, ...]:
        """从所有根到 Effect 枚举并保留实际发生 Session 转换的路径。"""
        roots = tuple(node for node, degree in self._context.graph.in_degree() if degree == 0)
        effects = tuple(
            reference for reference in self._context.nodes if reference.kind is GraphNodeKind.EFFECT
        )
        paths = self.search(PathRequest(roots, effects, max_depth))
        return tuple(path for path in paths if path.cross_session_count > 0)

    def skill_effects(self, skill: GraphNodeRef, max_depth: int) -> tuple[SecurityPath, ...]:
        """从一个 Skill Principal 到全部 Effect 查询候选影响路径。"""
        effects = tuple(
            reference for reference in self._context.nodes if reference.kind is GraphNodeKind.EFFECT
        )
        paths = self.search(PathRequest((skill,), effects, max_depth))
        return tuple(
            path
            for path in paths
            if any(edge.relation is SecurityRelation.INFLUENCE_CANDIDATE for edge in path.edges)
        )

    def _materialize(self, references: tuple[GraphNodeRef, ...]) -> SecurityPath:
        nodes = tuple(self._context.nodes[reference] for reference in references)
        edges = tuple(
            self._context.edges[(source, target)] for source, target in pairwise(references)
        )
        sessions = ordered_session_trace(edges)
        evidence = _unique(event_id for edge in edges for event_id in edge.evidence_event_ids)
        cross_sessions = max(len(sessions) - 1, 0)
        boundary_depth = calculate_boundary_depth(edges, cross_sessions)
        cutoff = latest_event_time(nodes)
        revoked_ids, revocation_events = self._path_revocations(references, cutoff)
        grants, skills, tools = group_path_nodes(nodes)
        return SecurityPath(
            nodes=nodes,
            edges=edges,
            session_ids=sessions,
            evidence_event_ids=evidence,
            boundary_depth=boundary_depth,
            cross_session_count=cross_sessions,
            revoked_origin_ids=revoked_ids,
            revocation_event_ids=revocation_events,
            grant_ids=grants,
            skill_ids=skills,
            tool_ids=tools,
        )

    def _path_revocations(
        self,
        references: tuple[GraphNodeRef, ...],
        cutoff: datetime | None,
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        active = tuple(
            fact
            for reference in references
            for fact in self._context.revocations.get(reference, ())
            if cutoff is None or fact.timestamp <= cutoff
        )
        return (
            _unique(fact.target.node_id for fact in active),
            _unique(fact.event_id for fact in active),
        )


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _ref_key(reference: GraphNodeRef) -> tuple[str, str]:
    return reference.kind.value, reference.node_id


def _path_key(path: tuple[GraphNodeRef, ...]) -> tuple[int, tuple[tuple[str, str], ...]]:
    return len(path), tuple(_ref_key(reference) for reference in path)
