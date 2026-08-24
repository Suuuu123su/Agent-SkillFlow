"""来源图节点、边、路径与导出的强类型合同。"""

from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal, TypeAlias, assert_never

from pydantic import Field

from skillflow.graph.enums import (
    BoundaryKind,
    GraphNodeKind,
    ProvenanceRelation,
    SecurityRelation,
)
from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.enums import (
    ArtifactType,
    CapabilityAction,
    EventType,
    PrincipalType,
    TrustLevel,
)


class GraphNodeRef(StrictModel):
    """避免不同节点类型的原始 ID 相撞。"""

    kind: GraphNodeKind
    node_id: NonEmptyStr


class _GraphNodeBase(StrictModel):
    node_id: NonEmptyStr
    run_id: NonEmptyStr


class ArtifactGraphNode(_GraphNodeBase):
    """脱敏 Artifact 节点。"""

    kind: Literal[GraphNodeKind.ARTIFACT] = GraphNodeKind.ARTIFACT
    artifact_type: ArtifactType
    trust: TrustLevel
    created_session_id: NonEmptyStr


class EventGraphNode(_GraphNodeBase):
    """保留会话和时间证据的 Event 节点。"""

    kind: Literal[GraphNodeKind.EVENT] = GraphNodeKind.EVENT
    event_type: EventType
    session_id: NonEmptyStr
    timestamp: datetime


class PrincipalGraphNode(_GraphNodeBase):
    """保守类型化的主体节点。"""

    kind: Literal[GraphNodeKind.PRINCIPAL] = GraphNodeKind.PRINCIPAL
    principal_type: PrincipalType | None


class GrantGraphNode(_GraphNodeBase):
    """由签发事件或 Decision 引用建立的 Grant 节点。"""

    kind: Literal[GraphNodeKind.GRANT] = GraphNodeKind.GRANT


class DecisionGraphNode(_GraphNodeBase):
    """不复制理由正文的 Decision 节点。"""

    kind: Literal[GraphNodeKind.DECISION] = GraphNodeKind.DECISION
    authorized: bool
    executed: bool


class EffectGraphNode(_GraphNodeBase):
    """可作为查询端点的 Effect 节点。"""

    kind: Literal[GraphNodeKind.EFFECT] = GraphNodeKind.EFFECT
    action: CapabilityAction
    executed: bool


SecurityNode: TypeAlias = Annotated[
    ArtifactGraphNode
    | EventGraphNode
    | PrincipalGraphNode
    | GrantGraphNode
    | DecisionGraphNode
    | EffectGraphNode,
    Field(discriminator="kind"),
]


def node_ref(node: SecurityNode) -> GraphNodeRef:
    """把任一节点投影为可哈希引用。"""
    match node:
        case (
            ArtifactGraphNode(kind=kind, node_id=node_id)
            | EventGraphNode(kind=kind, node_id=node_id)
            | PrincipalGraphNode(kind=kind, node_id=node_id)
            | GrantGraphNode(kind=kind, node_id=node_id)
            | DecisionGraphNode(kind=kind, node_id=node_id)
            | EffectGraphNode(kind=kind, node_id=node_id)
        ):
            return GraphNodeRef(kind=kind, node_id=node_id)
        case _ as unreachable:
            assert_never(unreachable)


class ProvenanceEdge(StrictModel):
    """Artifact-Event 二部边及其唯一证据。"""

    source: GraphNodeRef
    target: GraphNodeRef
    relation: ProvenanceRelation
    session_id: NonEmptyStr
    evidence_event_id: NonEmptyStr


class SecurityEdge(StrictModel):
    """带会话、Event 证据和边界类型的语义边。"""

    source: GraphNodeRef
    target: GraphNodeRef
    relation: SecurityRelation
    session_ids: tuple[NonEmptyStr, ...]
    evidence_event_ids: tuple[NonEmptyStr, ...]
    boundaries: tuple[BoundaryKind, ...] = ()


class BoundaryDepth(StrictModel):
    """五类边界及总深度计数。"""

    context: int = Field(ge=0)
    memory: int = Field(ge=0)
    session: int = Field(ge=0)
    skill: int = Field(ge=0)
    tool: int = Field(ge=0)
    total: int = Field(ge=0)


class SecurityPath(StrictModel):
    """一次完整查询返回的可审计路径。"""

    nodes: tuple[SecurityNode, ...]
    edges: tuple[SecurityEdge, ...]
    session_ids: tuple[NonEmptyStr, ...]
    evidence_event_ids: tuple[NonEmptyStr, ...]
    boundary_depth: BoundaryDepth
    cross_session_count: int = Field(ge=0)
    revoked_origin_ids: tuple[NonEmptyStr, ...] = ()
    revocation_event_ids: tuple[NonEmptyStr, ...] = ()
    grant_ids: tuple[NonEmptyStr, ...] = ()
    skill_ids: tuple[NonEmptyStr, ...] = ()
    tool_ids: tuple[NonEmptyStr, ...] = ()

    @property
    def node_refs(self) -> tuple[GraphNodeRef, ...]:
        """返回不含节点属性的稳定路径引用。"""
        return tuple(node_ref(node) for node in self.nodes)


class SecurityGraphExport(StrictModel):
    """不包含 Blob、正文或任意 Event metadata 的 JSON 投影。"""

    run_id: NonEmptyStr
    nodes: tuple[SecurityNode, ...]
    provenance_edges: tuple[ProvenanceEdge, ...]
    security_edges: tuple[SecurityEdge, ...]


@dataclass(frozen=True, slots=True)
class RevocationFact:
    """不改写历史图的事件时间撤销事实。"""

    target: GraphNodeRef
    event_id: str
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class GraphBuildData:
    """GraphBuilder 交给只读查询层的冻结数据。"""

    run_id: str
    nodes: tuple[SecurityNode, ...]
    provenance_edges: tuple[ProvenanceEdge, ...]
    security_edges: tuple[SecurityEdge, ...]
    revocations: tuple[RevocationFact, ...]
