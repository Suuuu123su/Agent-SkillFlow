"""投影 Principal、Grant 与撤销相关的特殊事件边。"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, assert_never

from pydantic import TypeAdapter, ValidationError

from skillflow.graph.assembly import GraphAssembler
from skillflow.graph.enums import BoundaryKind, GraphNodeKind, SecurityRelation
from skillflow.graph.errors import GraphBuildError
from skillflow.graph.models import (
    GrantGraphNode,
    GraphNodeRef,
    PrincipalGraphNode,
    RevocationFact,
    SecurityEdge,
)
from skillflow.models.base import NonEmptyStr
from skillflow.models.enums import EventType, PrincipalType
from skillflow.models.events import SecurityEvent
from skillflow.models.provenance import Artifact

TEXT_ADAPTER: Final[TypeAdapter[str]] = TypeAdapter(NonEmptyStr)


@dataclass(frozen=True, slots=True)
class _PrincipalTransition:
    """主体与事件之间的一次有向边界转换。"""

    source: GraphNodeRef
    target: GraphNodeRef
    boundary: BoundaryKind


def project_special_event(
    assembler: GraphAssembler,
    event: SecurityEvent,
    artifacts: Mapping[str, Artifact],
) -> None:
    """投影不能仅由 Artifact 输入输出表达的主体、授权与撤销边。"""
    event_ref = _ref(GraphNodeKind.EVENT, event.event_id)
    actor_ref = _ref(GraphNodeKind.PRINCIPAL, event.actor_id)
    match event.event_type:
        case EventType.SKILL_RETURN:
            _add_transition(
                assembler,
                event,
                _PrincipalTransition(actor_ref, event_ref, BoundaryKind.SKILL),
            )
        case EventType.SKILL_INVOKE:
            _add_transition(
                assembler,
                event,
                _PrincipalTransition(event_ref, actor_ref, BoundaryKind.SKILL),
            )
        case EventType.TOOL_CALL_REQUEST:
            _project_tool_request(
                assembler,
                event,
                _needs_actor_edge(event, artifacts),
            )
        case EventType.TOOL_CALL_RESULT:
            _add_transition(
                assembler,
                event,
                _PrincipalTransition(actor_ref, event_ref, BoundaryKind.TOOL),
            )
        case EventType.AUTH_GRANT:
            _project_grant(assembler, event, event_ref)
        case EventType.SKILL_REVOKE:
            target = assembler.add_node(
                PrincipalGraphNode(
                    node_id=_metadata_text(event, "skill_id"),
                    run_id=event.run_id,
                    principal_type=PrincipalType.SKILL,
                )
            )
            _add_revocation(assembler, target, event)
        case EventType.AUTH_REVOKE:
            target = assembler.add_node(
                GrantGraphNode(
                    node_id=_metadata_text(event, "grant_id"),
                    run_id=event.run_id,
                )
            )
            _add_revocation(assembler, target, event)
        case (
            EventType.RUN_START
            | EventType.RUN_END
            | EventType.SESSION_START
            | EventType.SESSION_END
            | EventType.SKILL_INSTALL
            | EventType.SKILL_LOAD
            | EventType.SKILL_UNLOAD
            | EventType.CONTEXT_ADD
            | EventType.CONTEXT_READ
            | EventType.CONTEXT_SUMMARIZE
            | EventType.MEMORY_WRITE
            | EventType.MEMORY_READ
            | EventType.MEMORY_DELETE
            | EventType.FILE_READ
            | EventType.FILE_WRITE
            | EventType.TOOL_CALL_ALLOW
            | EventType.TOOL_CALL_DENY
            | EventType.AUTH_CLAIM_OBSERVED
            | EventType.ARTIFACT_REGISTER
            | EventType.ARTIFACT_DERIVE
            | EventType.SENSITIVE_EFFECT
        ):
            pass
        case _ as unreachable:
            assert_never(unreachable)


def _project_tool_request(
    assembler: GraphAssembler,
    event: SecurityEvent,
    needs_actor_edge: bool,
) -> None:
    event_ref = _ref(GraphNodeKind.EVENT, event.event_id)
    if needs_actor_edge:
        actor_ref = _ref(GraphNodeKind.PRINCIPAL, event.actor_id)
        _add_transition(
            assembler,
            event,
            _PrincipalTransition(actor_ref, event_ref, BoundaryKind.SKILL),
        )
    tool_id = _metadata_text(event, "tool")
    tool_id = tool_id if tool_id.startswith("tool:") else f"tool:{tool_id}"
    tool_ref = assembler.add_node(
        PrincipalGraphNode(
            node_id=tool_id,
            run_id=event.run_id,
            principal_type=PrincipalType.TOOL,
        )
    )
    _add_transition(
        assembler,
        event,
        _PrincipalTransition(event_ref, tool_ref, BoundaryKind.TOOL),
    )


def _needs_actor_edge(
    event: SecurityEvent,
    artifacts: Mapping[str, Artifact],
) -> bool:
    return not event.input_artifact_ids or not any(
        event.actor_id in artifacts[artifact_id].observed_label.origins
        for artifact_id in event.input_artifact_ids
    )


def _project_grant(
    assembler: GraphAssembler,
    event: SecurityEvent,
    event_ref: GraphNodeRef,
) -> None:
    grant_ref = assembler.add_node(
        GrantGraphNode(
            node_id=_metadata_text(event, "grant_id"),
            run_id=event.run_id,
        )
    )
    assembler.add_security_edge(
        SecurityEdge(
            source=event_ref,
            target=grant_ref,
            relation=SecurityRelation.AUTHORIZE,
            session_ids=(event.session_id,),
            evidence_event_ids=(event.event_id,),
        )
    )


def _add_transition(
    assembler: GraphAssembler,
    event: SecurityEvent,
    transition: _PrincipalTransition,
) -> None:
    assembler.add_security_edge(
        SecurityEdge(
            source=transition.source,
            target=transition.target,
            relation=SecurityRelation.INVOKE,
            session_ids=(event.session_id,),
            evidence_event_ids=(event.event_id,),
            boundaries=(transition.boundary,),
        )
    )


def _add_revocation(
    assembler: GraphAssembler,
    target: GraphNodeRef,
    event: SecurityEvent,
) -> None:
    event_ref = _ref(GraphNodeKind.EVENT, event.event_id)
    assembler.add_security_edge(
        SecurityEdge(
            source=target,
            target=event_ref,
            relation=SecurityRelation.REVOKE,
            session_ids=(event.session_id,),
            evidence_event_ids=(event.event_id,),
        )
    )
    assembler.add_revocation(RevocationFact(target, event.event_id, event.timestamp))


def _metadata_text(event: SecurityEvent, key: str) -> str:
    try:
        return TEXT_ADAPTER.validate_python(event.metadata.get(key))
    except ValidationError as error:
        raise GraphBuildError(event.event_id, f"metadata 缺少有效 {key}") from error


def _ref(kind: GraphNodeKind, node_id: str) -> GraphNodeRef:
    return GraphNodeRef(kind=kind, node_id=node_id)
