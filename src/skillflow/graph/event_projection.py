"""把 Event 与 Artifact 投影为二部边和事件语义边。"""

from collections.abc import Mapping

from skillflow.graph.assembly import GraphAssembler
from skillflow.graph.enums import (
    BoundaryKind,
    GraphNodeKind,
    ProvenanceRelation,
)
from skillflow.graph.facts import RunGraphFacts
from skillflow.graph.models import (
    ArtifactGraphNode,
    EventGraphNode,
    GraphNodeRef,
    PrincipalGraphNode,
    ProvenanceEdge,
    SecurityEdge,
)
from skillflow.graph.semantics import event_semantics, infer_actor_type
from skillflow.graph.special_event_projection import project_special_event
from skillflow.models.enums import ArtifactType
from skillflow.models.events import SecurityEvent
from skillflow.models.provenance import Artifact


def project_events(assembler: GraphAssembler, facts: RunGraphFacts) -> None:
    """先登记节点，再生成可按 ID 验证的事件边。"""
    artifacts = {artifact.artifact_id: artifact for artifact in facts.artifacts}
    for artifact in facts.artifacts:
        assembler.add_node(
            ArtifactGraphNode(
                node_id=artifact.artifact_id,
                run_id=facts.run_id,
                artifact_type=artifact.artifact_type,
                trust=artifact.observed_label.trust,
                created_session_id=artifact.observed_label.created_session_id,
            )
        )
    for event in facts.events:
        assembler.add_node(
            EventGraphNode(
                node_id=event.event_id,
                run_id=facts.run_id,
                event_type=event.event_type,
                session_id=event.session_id,
                timestamp=event.timestamp,
            )
        )
        assembler.add_node(
            PrincipalGraphNode(
                node_id=event.actor_id,
                run_id=facts.run_id,
                principal_type=infer_actor_type(event),
            )
        )
    for event in facts.events:
        _project_provenance(assembler, event)
        _project_semantics(assembler, event, artifacts)
        project_special_event(assembler, event, artifacts)


def _project_provenance(assembler: GraphAssembler, event: SecurityEvent) -> None:
    event_ref = _ref(GraphNodeKind.EVENT, event.event_id)
    for artifact_id in event.input_artifact_ids:
        assembler.add_provenance_edge(
            ProvenanceEdge(
                source=_ref(GraphNodeKind.ARTIFACT, artifact_id),
                target=event_ref,
                relation=ProvenanceRelation.USED,
                session_id=event.session_id,
                evidence_event_id=event.event_id,
            )
        )
    for artifact_id in event.output_artifact_ids:
        assembler.add_provenance_edge(
            ProvenanceEdge(
                source=event_ref,
                target=_ref(GraphNodeKind.ARTIFACT, artifact_id),
                relation=ProvenanceRelation.GENERATED,
                session_id=event.session_id,
                evidence_event_id=event.event_id,
            )
        )


def _project_semantics(
    assembler: GraphAssembler,
    event: SecurityEvent,
    artifacts: Mapping[str, Artifact],
) -> None:
    semantics = event_semantics(event.event_type)
    event_ref = _ref(GraphNodeKind.EVENT, event.event_id)
    input_boundaries = () if semantics.boundary is None else (semantics.boundary,)
    if semantics.input_relation is not None:
        for artifact_id in event.input_artifact_ids:
            assembler.add_security_edge(
                SecurityEdge(
                    source=_ref(GraphNodeKind.ARTIFACT, artifact_id),
                    target=event_ref,
                    relation=semantics.input_relation,
                    session_ids=(event.session_id,),
                    evidence_event_ids=(event.event_id,),
                    boundaries=input_boundaries,
                )
            )
    if semantics.output_relation is None:
        return
    for artifact_id in event.output_artifact_ids:
        output_boundary = _output_boundaries(event, artifacts[artifact_id])
        assembler.add_security_edge(
            SecurityEdge(
                source=event_ref,
                target=_ref(GraphNodeKind.ARTIFACT, artifact_id),
                relation=semantics.output_relation,
                session_ids=(event.session_id,),
                evidence_event_ids=(event.event_id,),
                boundaries=output_boundary,
            )
        )


def _output_boundaries(event: SecurityEvent, artifact: Artifact) -> tuple[BoundaryKind, ...]:
    semantics = event_semantics(event.event_type)
    boundaries: list[BoundaryKind] = []
    if not event.input_artifact_ids and semantics.boundary is not None:
        boundaries.append(semantics.boundary)
    if (
        artifact.artifact_type is ArtifactType.CONTEXT
        and semantics.boundary is not BoundaryKind.CONTEXT
    ):
        boundaries.append(BoundaryKind.CONTEXT)
    if artifact.artifact_type is ArtifactType.MEMORY and semantics.boundary is None:
        boundaries.append(BoundaryKind.MEMORY)
    return tuple(boundaries)


def _ref(kind: GraphNodeKind, node_id: str) -> GraphNodeRef:
    return GraphNodeRef(kind=kind, node_id=node_id)
