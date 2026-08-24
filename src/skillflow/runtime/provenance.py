"""Observed Plane 的受控来源缺陷注入。"""

from typing import assert_never

from skillflow.models.enums import EventType, ProvenanceMode

DERIVATION_EVENTS = frozenset(
    {
        EventType.CONTEXT_READ,
        EventType.CONTEXT_SUMMARIZE,
        EventType.MEMORY_WRITE,
        EventType.MEMORY_READ,
        EventType.FILE_WRITE,
        EventType.SKILL_RETURN,
        EventType.TOOL_CALL_REQUEST,
        EventType.TOOL_CALL_RESULT,
        EventType.ARTIFACT_DERIVE,
    }
)
MEMORY_EVENTS = frozenset({EventType.MEMORY_WRITE, EventType.MEMORY_READ})


def observed_origins(
    mode: ProvenanceMode,
    event_type: EventType,
    origins: frozenset[str],
) -> frozenset[str]:
    """只在 Observed 标签上应用预注册的来源丢失模式。"""
    match mode:
        case ProvenanceMode.PRESERVE:
            return origins
        case ProvenanceMode.DROP_ON_DERIVE:
            return frozenset() if event_type in DERIVATION_EVENTS else origins
        case ProvenanceMode.DROP_ON_MEMORY:
            return frozenset() if event_type in MEMORY_EVENTS else origins
        case _ as unreachable:
            assert_never(unreachable)
