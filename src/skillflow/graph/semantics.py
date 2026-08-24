"""把封闭 EventType 机械映射为图语义。"""

from dataclasses import dataclass
from typing import Literal, TypeAlias, assert_never

from skillflow.graph.enums import BoundaryKind, SecurityRelation
from skillflow.models.enums import EventType, PrincipalType
from skillflow.models.events import SecurityEvent

SkillEventType: TypeAlias = Literal[
    EventType.SKILL_INSTALL,
    EventType.SKILL_LOAD,
    EventType.SKILL_INVOKE,
    EventType.SKILL_RETURN,
    EventType.SKILL_REVOKE,
    EventType.SKILL_UNLOAD,
]
ContextEventType: TypeAlias = Literal[
    EventType.CONTEXT_ADD,
    EventType.CONTEXT_READ,
    EventType.CONTEXT_SUMMARIZE,
]
MemoryEventType: TypeAlias = Literal[
    EventType.MEMORY_WRITE,
    EventType.MEMORY_READ,
    EventType.MEMORY_DELETE,
]
FileEventType: TypeAlias = Literal[EventType.FILE_READ, EventType.FILE_WRITE]
ToolEventType: TypeAlias = Literal[
    EventType.TOOL_CALL_REQUEST,
    EventType.TOOL_CALL_ALLOW,
    EventType.TOOL_CALL_DENY,
    EventType.TOOL_CALL_RESULT,
]
ArtifactEventType: TypeAlias = Literal[
    EventType.ARTIFACT_REGISTER,
    EventType.ARTIFACT_DERIVE,
    EventType.SENSITIVE_EFFECT,
]


@dataclass(frozen=True, slots=True)
class EventSemantics:
    """一个 Event 的输入、输出边及主要边界。"""

    input_relation: SecurityRelation | None
    output_relation: SecurityRelation | None
    boundary: BoundaryKind | None


def event_semantics(event_type: EventType) -> EventSemantics:
    """穷尽映射全部事件，新增事件不会静默落入默认分支。"""
    match event_type:
        case (
            EventType.RUN_START
            | EventType.RUN_END
            | EventType.SESSION_START
            | EventType.SESSION_END
            | EventType.AUTH_CLAIM_OBSERVED
            | EventType.AUTH_GRANT
            | EventType.AUTH_REVOKE
        ):
            semantics = EventSemantics(None, None, None)
        case (
            EventType.SKILL_INSTALL
            | EventType.SKILL_LOAD
            | EventType.SKILL_INVOKE
            | EventType.SKILL_RETURN
            | EventType.SKILL_REVOKE
            | EventType.SKILL_UNLOAD
        ):
            semantics = _skill_semantics(event_type)
        case EventType.CONTEXT_ADD | EventType.CONTEXT_READ | EventType.CONTEXT_SUMMARIZE:
            semantics = _context_semantics(event_type)
        case EventType.MEMORY_WRITE | EventType.MEMORY_READ | EventType.MEMORY_DELETE:
            semantics = _memory_semantics(event_type)
        case EventType.FILE_READ | EventType.FILE_WRITE:
            semantics = _file_semantics(event_type)
        case (
            EventType.TOOL_CALL_REQUEST
            | EventType.TOOL_CALL_ALLOW
            | EventType.TOOL_CALL_DENY
            | EventType.TOOL_CALL_RESULT
        ):
            semantics = _tool_semantics(event_type)
        case EventType.ARTIFACT_REGISTER | EventType.ARTIFACT_DERIVE | EventType.SENSITIVE_EFFECT:
            semantics = _artifact_semantics(event_type)
        case _ as unreachable:
            assert_never(unreachable)
    return semantics


def _skill_semantics(event_type: SkillEventType) -> EventSemantics:
    match event_type:
        case EventType.SKILL_INVOKE:
            return EventSemantics(SecurityRelation.INVOKE, None, None)
        case EventType.SKILL_RETURN:
            return EventSemantics(
                SecurityRelation.INVOKE,
                SecurityRelation.DERIVE,
                None,
            )
        case (
            EventType.SKILL_INSTALL
            | EventType.SKILL_LOAD
            | EventType.SKILL_REVOKE
            | EventType.SKILL_UNLOAD
        ):
            return EventSemantics(None, None, None)
        case _ as unreachable:
            assert_never(unreachable)


def _context_semantics(event_type: ContextEventType) -> EventSemantics:
    match event_type:
        case EventType.CONTEXT_ADD:
            return EventSemantics(
                SecurityRelation.WRITE,
                SecurityRelation.WRITE,
                BoundaryKind.CONTEXT,
            )
        case EventType.CONTEXT_READ:
            return EventSemantics(
                SecurityRelation.READ,
                SecurityRelation.READ,
                BoundaryKind.CONTEXT,
            )
        case EventType.CONTEXT_SUMMARIZE:
            return EventSemantics(
                SecurityRelation.READ,
                SecurityRelation.DERIVE,
                BoundaryKind.CONTEXT,
            )
        case _ as unreachable:
            assert_never(unreachable)


def _memory_semantics(event_type: MemoryEventType) -> EventSemantics:
    match event_type:
        case EventType.MEMORY_WRITE:
            return EventSemantics(
                SecurityRelation.WRITE,
                SecurityRelation.PERSIST,
                BoundaryKind.MEMORY,
            )
        case EventType.MEMORY_READ:
            return EventSemantics(
                SecurityRelation.LOAD,
                SecurityRelation.READ,
                BoundaryKind.MEMORY,
            )
        case EventType.MEMORY_DELETE:
            return EventSemantics(SecurityRelation.WRITE, None, BoundaryKind.MEMORY)
        case _ as unreachable:
            assert_never(unreachable)


def _file_semantics(event_type: FileEventType) -> EventSemantics:
    match event_type:
        case EventType.FILE_READ:
            return EventSemantics(None, SecurityRelation.READ, None)
        case EventType.FILE_WRITE:
            return EventSemantics(
                SecurityRelation.WRITE,
                SecurityRelation.PERSIST,
                None,
            )
        case _ as unreachable:
            assert_never(unreachable)


def _tool_semantics(event_type: ToolEventType) -> EventSemantics:
    match event_type:
        case EventType.TOOL_CALL_REQUEST:
            return EventSemantics(
                SecurityRelation.INVOKE,
                SecurityRelation.DERIVE,
                None,
            )
        case EventType.TOOL_CALL_ALLOW | EventType.TOOL_CALL_DENY:
            return EventSemantics(SecurityRelation.AUTHORIZE, None, BoundaryKind.TOOL)
        case EventType.TOOL_CALL_RESULT:
            return EventSemantics(
                SecurityRelation.INVOKE,
                SecurityRelation.DERIVE,
                None,
            )
        case _ as unreachable:
            assert_never(unreachable)


def _artifact_semantics(event_type: ArtifactEventType) -> EventSemantics:
    match event_type:
        case EventType.ARTIFACT_REGISTER:
            return EventSemantics(None, SecurityRelation.DERIVE, None)
        case EventType.ARTIFACT_DERIVE:
            return EventSemantics(
                SecurityRelation.DERIVE,
                SecurityRelation.DERIVE,
                None,
            )
        case EventType.SENSITIVE_EFFECT:
            return EventSemantics(
                SecurityRelation.INFLUENCE_CANDIDATE,
                None,
                BoundaryKind.TOOL,
            )
        case _ as unreachable:
            assert_never(unreachable)


def infer_actor_type(event: SecurityEvent) -> PrincipalType | None:
    """只根据结构化 actor 与事件类型作保守推断。"""
    known = {
        PrincipalType.USER.value: PrincipalType.USER,
        PrincipalType.TRUSTED_POLICY.value: PrincipalType.TRUSTED_POLICY,
        PrincipalType.HARNESS.value: PrincipalType.HARNESS,
    }.get(event.actor_id)
    if known is not None:
        return known
    if event.actor_id.startswith("tool:"):
        return PrincipalType.TOOL
    match event.event_type:
        case (
            EventType.SKILL_INVOKE
            | EventType.SKILL_RETURN
            | EventType.CONTEXT_ADD
            | EventType.CONTEXT_READ
            | EventType.CONTEXT_SUMMARIZE
            | EventType.MEMORY_WRITE
            | EventType.MEMORY_READ
            | EventType.MEMORY_DELETE
            | EventType.FILE_READ
            | EventType.FILE_WRITE
            | EventType.TOOL_CALL_REQUEST
        ):
            return PrincipalType.SKILL
        case (
            EventType.RUN_START
            | EventType.RUN_END
            | EventType.SESSION_START
            | EventType.SESSION_END
            | EventType.SKILL_INSTALL
            | EventType.SKILL_LOAD
            | EventType.SKILL_REVOKE
            | EventType.SKILL_UNLOAD
            | EventType.TOOL_CALL_ALLOW
            | EventType.TOOL_CALL_DENY
            | EventType.TOOL_CALL_RESULT
            | EventType.AUTH_CLAIM_OBSERVED
            | EventType.AUTH_GRANT
            | EventType.AUTH_REVOKE
            | EventType.ARTIFACT_REGISTER
            | EventType.ARTIFACT_DERIVE
            | EventType.SENSITIVE_EFFECT
        ):
            return None
        case _ as unreachable:
            assert_never(unreachable)
