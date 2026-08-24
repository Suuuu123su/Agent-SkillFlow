from skillflow.graph.enums import GraphNodeKind, SecurityRelation
from skillflow.graph.models import GraphNodeRef, SecurityEdge
from skillflow.graph.path_analysis import ordered_session_trace


def test_ordered_session_trace_counts_reentry_as_a_second_crossing() -> None:
    edges = (
        _edge(1, ("session-a",)),
        _edge(2, ("session-a", "session-b")),
        _edge(3, ("session-b",)),
        _edge(4, ("session-a",)),
    )

    trace = ordered_session_trace(edges)

    assert trace == ("session-a", "session-b", "session-a")
    assert len(trace) - 1 == 2


def _edge(index: int, session_ids: tuple[str, ...]) -> SecurityEdge:
    return SecurityEdge(
        source=GraphNodeRef(kind=GraphNodeKind.EVENT, node_id=f"event-{index}"),
        target=GraphNodeRef(kind=GraphNodeKind.ARTIFACT, node_id=f"artifact-{index}"),
        relation=SecurityRelation.DERIVE,
        session_ids=session_ids,
        evidence_event_ids=(f"event-{index}",),
    )
