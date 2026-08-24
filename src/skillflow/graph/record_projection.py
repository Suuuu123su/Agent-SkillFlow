"""把 DecisionRecord、Grant 引用和 EffectRecord 投影为安全节点。"""

from collections.abc import Mapping
from dataclasses import dataclass

from skillflow.graph.assembly import GraphAssembler
from skillflow.graph.enums import GraphNodeKind, SecurityRelation
from skillflow.graph.errors import GraphBuildError
from skillflow.graph.facts import RunGraphFacts
from skillflow.graph.models import (
    DecisionGraphNode,
    EffectGraphNode,
    GrantGraphNode,
    GraphNodeRef,
    SecurityEdge,
)
from skillflow.models.effects import EffectRecord
from skillflow.models.events import DecisionRecord, SecurityEvent


@dataclass(frozen=True, slots=True)
class _RecordProjectionContext:
    """Record 投影共享的不可变索引。"""

    assembler: GraphAssembler
    run_id: str
    events: Mapping[str, SecurityEvent]
    decisions: Mapping[str, DecisionRecord]


def project_records(assembler: GraphAssembler, facts: RunGraphFacts) -> None:
    """连接 Grant→Decision→Effect 与实际结果 Event→Effect。"""
    events = {event.event_id: event for event in facts.events}
    decisions = {decision.decision_id: decision for decision in facts.decisions}
    context = _RecordProjectionContext(assembler, facts.run_id, events, decisions)
    for decision in facts.decisions:
        _project_decision(context, decision)
    for effect in facts.effects:
        _project_effect(context, effect)


def _project_decision(
    context: _RecordProjectionContext,
    decision: DecisionRecord,
) -> None:
    request = _require_event(context.events, decision.request_event_id)
    decision_ref = context.assembler.add_node(
        DecisionGraphNode(
            node_id=decision.decision_id,
            run_id=context.run_id,
            authorized=decision.authorized,
            executed=decision.executed,
        )
    )
    for grant_id in decision.matched_grant_ids:
        grant_ref = context.assembler.add_node(
            GrantGraphNode(node_id=grant_id, run_id=context.run_id)
        )
        context.assembler.add_security_edge(
            SecurityEdge(
                source=grant_ref,
                target=decision_ref,
                relation=SecurityRelation.AUTHORIZE,
                session_ids=(request.session_id,),
                evidence_event_ids=(request.event_id,),
            )
        )
    for artifact_id in decision.decision_basis_artifact_ids:
        context.assembler.add_security_edge(
            SecurityEdge(
                source=_ref(GraphNodeKind.ARTIFACT, artifact_id),
                target=decision_ref,
                relation=SecurityRelation.AUTHORIZE,
                session_ids=(request.session_id,),
                evidence_event_ids=(request.event_id,),
            )
        )


def _project_effect(
    context: _RecordProjectionContext,
    effect: EffectRecord,
) -> None:
    request = _require_event(context.events, effect.request_event_id)
    result = (
        request
        if effect.result_event_id is None
        else _require_event(context.events, effect.result_event_id)
    )
    if effect.decision_id not in context.decisions:
        raise GraphBuildError(effect.effect_id, "Effect 引用的 DecisionRecord 不存在")
    effect_ref = context.assembler.add_node(
        EffectGraphNode(
            node_id=effect.effect_id,
            run_id=context.run_id,
            action=effect.effect.action,
            executed=effect.executed,
        )
    )
    evidence = tuple(dict.fromkeys((request.event_id, result.event_id)))
    sessions = tuple(dict.fromkeys((request.session_id, result.session_id)))
    context.assembler.add_security_edge(
        SecurityEdge(
            source=_ref(GraphNodeKind.EVENT, result.event_id),
            target=effect_ref,
            relation=SecurityRelation.INFLUENCE_CANDIDATE,
            session_ids=sessions,
            evidence_event_ids=evidence,
        )
    )
    context.assembler.add_security_edge(
        SecurityEdge(
            source=_ref(GraphNodeKind.DECISION, effect.decision_id),
            target=effect_ref,
            relation=SecurityRelation.AUTHORIZE,
            session_ids=sessions,
            evidence_event_ids=evidence,
        )
    )


def _require_event(events: Mapping[str, SecurityEvent], event_id: str) -> SecurityEvent:
    try:
        return events[event_id]
    except KeyError as error:
        raise GraphBuildError(event_id, "Record 引用的 Event 不在当前 Run") from error


def _ref(kind: GraphNodeKind, node_id: str) -> GraphNodeRef:
    return GraphNodeRef(kind=kind, node_id=node_id)
