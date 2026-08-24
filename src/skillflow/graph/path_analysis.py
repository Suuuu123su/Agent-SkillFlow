"""计算安全路径的边界深度、节点分组与事件时间。"""

from datetime import datetime
from typing import assert_never

from skillflow.graph.enums import BoundaryKind
from skillflow.graph.models import (
    ArtifactGraphNode,
    BoundaryDepth,
    DecisionGraphNode,
    EffectGraphNode,
    EventGraphNode,
    GrantGraphNode,
    PrincipalGraphNode,
    SecurityEdge,
    SecurityNode,
)
from skillflow.models.enums import EventType, PrincipalType, TrustLevel


def ordered_session_trace(edges: tuple[SecurityEdge, ...]) -> tuple[str, ...]:
    """按路径顺序压缩相邻重复 Session，同时保留之后的重新进入。"""
    trace: list[str] = []
    for edge in edges:
        for session_id in edge.session_ids:
            if not trace or trace[-1] != session_id:
                trace.append(session_id)
    return tuple(trace)


def calculate_boundary_depth(
    edges: tuple[SecurityEdge, ...],
    session_count: int,
) -> BoundaryDepth:
    """按 Context、Memory、Session、Skill、Tool 的穿越次数计算深度。"""
    boundaries = tuple(boundary for edge in edges for boundary in edge.boundaries)
    context = boundaries.count(BoundaryKind.CONTEXT)
    memory = boundaries.count(BoundaryKind.MEMORY)
    skill = boundaries.count(BoundaryKind.SKILL)
    tool = boundaries.count(BoundaryKind.TOOL)
    total = context + memory + session_count + skill + tool
    return BoundaryDepth(
        context=context,
        memory=memory,
        session=session_count,
        skill=skill,
        tool=tool,
        total=total,
    )


def latest_event_time(nodes: tuple[SecurityNode, ...]) -> datetime | None:
    """返回路径内最后一个 Event 的时间，供事件时间撤销判断使用。"""
    timestamps: list[datetime] = []
    for node in nodes:
        match node:
            case EventGraphNode(timestamp=timestamp):
                timestamps.append(timestamp)
            case (
                ArtifactGraphNode()
                | PrincipalGraphNode()
                | GrantGraphNode()
                | DecisionGraphNode()
                | EffectGraphNode()
            ):
                pass
            case _ as unreachable:
                assert_never(unreachable)
    return max(timestamps, default=None)


def group_path_nodes(
    nodes: tuple[SecurityNode, ...],
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """按首次出现次序收集 Grant、Skill 与 Tool 节点 ID。"""
    grants: list[str] = []
    skills: list[str] = []
    tools: list[str] = []
    for node in nodes:
        match node:
            case GrantGraphNode(node_id=node_id):
                grants.append(node_id)
            case PrincipalGraphNode(node_id=node_id, principal_type=PrincipalType.SKILL):
                skills.append(node_id)
            case PrincipalGraphNode(node_id=node_id, principal_type=PrincipalType.TOOL):
                tools.append(node_id)
            case (
                ArtifactGraphNode()
                | EventGraphNode()
                | PrincipalGraphNode()
                | DecisionGraphNode()
                | EffectGraphNode()
            ):
                pass
            case _ as unreachable:
                assert_never(unreachable)
    return _unique(grants), _unique(skills), _unique(tools)


def is_untrusted_artifact(node: SecurityNode) -> bool:
    """判断节点是否为事实源明确标注的不可信 Artifact。"""
    match node:
        case ArtifactGraphNode(trust=trust):
            return trust is TrustLevel.UNTRUSTED
        case (
            EventGraphNode()
            | PrincipalGraphNode()
            | GrantGraphNode()
            | DecisionGraphNode()
            | EffectGraphNode()
        ):
            return False
        case _ as unreachable:
            assert_never(unreachable)


def is_auth_grant_event(node: SecurityNode) -> bool:
    """判断节点是否为 AUTH_GRANT Event。"""
    match node:
        case EventGraphNode(event_type=event_type):
            return event_type is EventType.AUTH_GRANT
        case (
            ArtifactGraphNode()
            | PrincipalGraphNode()
            | GrantGraphNode()
            | DecisionGraphNode()
            | EffectGraphNode()
        ):
            return False
        case _ as unreachable:
            assert_never(unreachable)


def _unique(values: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))
