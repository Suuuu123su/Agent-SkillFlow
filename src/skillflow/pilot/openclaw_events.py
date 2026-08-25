"""把 OpenClaw 观察插件 JSONL 转换成统一 SecurityEvent。"""

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Final

from pydantic import JsonValue, ValidationError

from skillflow.models.effects import CapabilityEffect
from skillflow.models.enums import EventType
from skillflow.models.events import SecurityEvent
from skillflow.pilot.errors import OpenClawEventFileError
from skillflow.pilot.models import EFFECT_KINDS, OpenClawEventKind, OpenClawRawEvent

EVENT_TYPE: Final[dict[OpenClawEventKind, EventType]] = {
    OpenClawEventKind.CONTEXT_READ: EventType.CONTEXT_READ,
    OpenClawEventKind.SKILL_LOAD: EventType.SKILL_LOAD,
    OpenClawEventKind.SKILL_INVOKE: EventType.SKILL_INVOKE,
    OpenClawEventKind.SKILL_RETURN: EventType.SKILL_RETURN,
    OpenClawEventKind.SKILL_REVOKE: EventType.SKILL_REVOKE,
    OpenClawEventKind.TOOL_REQUEST: EventType.TOOL_CALL_REQUEST,
    OpenClawEventKind.TOOL_RESULT: EventType.TOOL_CALL_RESULT,
    OpenClawEventKind.FILE_READ: EventType.FILE_READ,
    OpenClawEventKind.MEMORY_READ: EventType.MEMORY_READ,
    OpenClawEventKind.MEMORY_WRITE: EventType.MEMORY_WRITE,
    OpenClawEventKind.SAFE_EFFECT: EventType.SENSITIVE_EFFECT,
}


def load_openclaw_events(path: Path) -> tuple[OpenClawRawEvent, ...]:
    """逐行解析原始日志，空行和非法行均拒绝。"""
    events: list[OpenClawRawEvent] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                raise OpenClawEventFileError.blank_line(line_number)
            try:
                events.append(OpenClawRawEvent.model_validate_json(line))
            except (ValidationError, json.JSONDecodeError) as error:
                raise OpenClawEventFileError.invalid_line(line_number, str(error)) from error
    sequences = tuple(item.sequence for item in events)
    if sequences != tuple(range(len(events))):
        raise OpenClawEventFileError.sequence_invalid()
    return tuple(events)


def translate_openclaw_events(
    events: Iterable[OpenClawRawEvent],
) -> tuple[SecurityEvent, ...]:
    """机械转换；不读取 OpenClaw SDK，也不改变核心模型。"""
    return tuple(_translate(event) for event in events)


def _translate(raw: OpenClawRawEvent) -> SecurityEvent:
    requested_effect = None
    if raw.kind in EFFECT_KINDS:
        if (
            raw.action is None
            or raw.sink is None
            or raw.scope is None
            or raw.lifetime is None
            or raw.sensitivity is None
        ):
            raise OpenClawEventFileError.effect_incomplete()
        requested_effect = CapabilityEffect(
            source=raw.source,
            action=raw.action,
            sink=raw.sink,
            scope=raw.scope,
            lifetime=raw.lifetime,
            sensitivity=raw.sensitivity,
        )
    metadata: dict[str, JsonValue] = {
        "adapter": "openclaw",
        "raw_sequence": raw.sequence,
        "platform_hook": raw.platform_hook,
        "origin_ids": list(raw.origin_ids),
    }
    optional_metadata: tuple[tuple[str, JsonValue | None], ...] = (
        ("skill_id", raw.skill_id),
        ("tool_name", raw.tool_name),
        ("resource", None if raw.resource is None else raw.resource.root),
        ("effect_alias", raw.effect_alias),
        ("receipt_id", raw.receipt_id),
        ("executed", raw.executed),
        ("policy_fact", raw.policy_fact),
    )
    metadata.update({key: value for key, value in optional_metadata if value is not None})
    return SecurityEvent(
        event_id=f"t15:{raw.run_id}:{raw.sequence}",
        run_id=raw.run_id,
        task_id=raw.task_id,
        session_id=raw.session_id,
        call_id=raw.call_id,
        timestamp=raw.timestamp,
        event_type=EVENT_TYPE[raw.kind],
        actor_id=raw.actor_id,
        requested_effect=requested_effect,
        metadata=metadata,
    )
