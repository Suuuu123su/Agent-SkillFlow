from datetime import UTC, datetime

import pytest

from skillflow.graph.enums import BoundaryKind, SecurityRelation
from skillflow.graph.semantics import EventSemantics, event_semantics, infer_actor_type
from skillflow.models.enums import EventType, PrincipalType
from skillflow.models.events import SecurityEvent

NONE = EventSemantics(None, None, None)
EXPECTED = {
    EventType.RUN_START: NONE,
    EventType.RUN_END: NONE,
    EventType.SESSION_START: NONE,
    EventType.SESSION_END: NONE,
    EventType.AUTH_CLAIM_OBSERVED: NONE,
    EventType.AUTH_GRANT: NONE,
    EventType.AUTH_REVOKE: NONE,
    EventType.SKILL_INSTALL: NONE,
    EventType.SKILL_LOAD: NONE,
    EventType.SKILL_INVOKE: EventSemantics(SecurityRelation.INVOKE, None, None),
    EventType.SKILL_RETURN: EventSemantics(SecurityRelation.INVOKE, SecurityRelation.DERIVE, None),
    EventType.SKILL_REVOKE: NONE,
    EventType.SKILL_UNLOAD: NONE,
    EventType.CONTEXT_ADD: EventSemantics(
        SecurityRelation.WRITE, SecurityRelation.WRITE, BoundaryKind.CONTEXT
    ),
    EventType.CONTEXT_READ: EventSemantics(
        SecurityRelation.READ, SecurityRelation.READ, BoundaryKind.CONTEXT
    ),
    EventType.CONTEXT_SUMMARIZE: EventSemantics(
        SecurityRelation.READ, SecurityRelation.DERIVE, BoundaryKind.CONTEXT
    ),
    EventType.MEMORY_WRITE: EventSemantics(
        SecurityRelation.WRITE, SecurityRelation.PERSIST, BoundaryKind.MEMORY
    ),
    EventType.MEMORY_READ: EventSemantics(
        SecurityRelation.LOAD, SecurityRelation.READ, BoundaryKind.MEMORY
    ),
    EventType.MEMORY_DELETE: EventSemantics(SecurityRelation.WRITE, None, BoundaryKind.MEMORY),
    EventType.FILE_READ: EventSemantics(None, SecurityRelation.READ, None),
    EventType.FILE_WRITE: EventSemantics(SecurityRelation.WRITE, SecurityRelation.PERSIST, None),
    EventType.TOOL_CALL_REQUEST: EventSemantics(
        SecurityRelation.INVOKE, SecurityRelation.DERIVE, None
    ),
    EventType.TOOL_CALL_ALLOW: EventSemantics(SecurityRelation.AUTHORIZE, None, BoundaryKind.TOOL),
    EventType.TOOL_CALL_DENY: EventSemantics(SecurityRelation.AUTHORIZE, None, BoundaryKind.TOOL),
    EventType.TOOL_CALL_RESULT: EventSemantics(
        SecurityRelation.INVOKE, SecurityRelation.DERIVE, None
    ),
    EventType.ARTIFACT_REGISTER: EventSemantics(None, SecurityRelation.DERIVE, None),
    EventType.ARTIFACT_DERIVE: EventSemantics(
        SecurityRelation.DERIVE, SecurityRelation.DERIVE, None
    ),
    EventType.SENSITIVE_EFFECT: EventSemantics(
        SecurityRelation.INFLUENCE_CANDIDATE, None, BoundaryKind.TOOL
    ),
}


@pytest.mark.parametrize("event_type", tuple(EventType))
def test_every_closed_event_type_has_exact_security_semantics(event_type: EventType) -> None:
    assert set(EXPECTED) == set(EventType)
    assert event_semantics(event_type) == EXPECTED[event_type]


@pytest.mark.parametrize(
    ("actor_id", "event_type", "expected"),
    [
        ("user", EventType.RUN_START, PrincipalType.USER),
        ("trusted_policy", EventType.AUTH_GRANT, PrincipalType.TRUSTED_POLICY),
        ("harness", EventType.RUN_END, PrincipalType.HARNESS),
        ("tool:http_send", EventType.TOOL_CALL_RESULT, PrincipalType.TOOL),
        ("skill-a", EventType.CONTEXT_READ, PrincipalType.SKILL),
        ("skill-a", EventType.MEMORY_WRITE, PrincipalType.SKILL),
        ("unknown", EventType.SENSITIVE_EFFECT, None),
    ],
)
def test_actor_inference_is_conservative(
    actor_id: str,
    event_type: EventType,
    expected: PrincipalType | None,
) -> None:
    event = SecurityEvent(
        event_id="event-t14",
        run_id="run-t14",
        task_id="task-t14",
        session_id="session-t14",
        timestamp=datetime(2026, 8, 25, tzinfo=UTC),
        event_type=event_type,
        actor_id=actor_id,
    )

    assert infer_actor_type(event) is expected
