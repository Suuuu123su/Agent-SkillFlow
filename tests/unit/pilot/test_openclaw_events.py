from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from skillflow.models.enums import CapabilityAction, EventType, Lifetime, Scope
from skillflow.pilot.errors import OpenClawEventFileError
from skillflow.pilot.models import OpenClawEventKind, OpenClawRawEvent
from skillflow.pilot.openclaw_events import load_openclaw_events, translate_openclaw_events


def _raw_event(**updates: object) -> OpenClawRawEvent:
    payload: dict[str, object] = {
        "schema_version": "0.1",
        "sequence": 7,
        "timestamp": datetime(2026, 8, 25, tzinfo=UTC),
        "kind": OpenClawEventKind.SAFE_EFFECT,
        "run_id": "openclaw-b0",
        "task_id": "task-b0",
        "session_id": "session-0",
        "call_id": "call-7",
        "actor_id": "summary-reader",
        "platform_hook": "after_tool_call",
        "tool_name": "skillflow_safe_sink",
        "effect_alias": "report-send",
        "receipt_id": "receipt-call-7",
        "origin_ids": ["asset:report"],
        "executed": True,
        "action": CapabilityAction.NETWORK_SEND,
        "source": "context:/task",
        "sink": "mock://external",
        "scope": Scope.EXACT_SINK,
        "lifetime": Lifetime.CALL,
        "sensitivity": 1,
        "policy_fact": "platform_executed_no_grant_fact",
    }
    payload.update(updates)
    return OpenClawRawEvent.model_validate(payload)


def test_safe_sink_event_becomes_unified_security_event() -> None:
    event = translate_openclaw_events((_raw_event(),))[0]

    assert event.event_type is EventType.SENSITIVE_EFFECT
    assert event.call_id == "call-7"
    assert event.requested_effect is not None
    assert event.requested_effect.action is CapabilityAction.NETWORK_SEND
    assert event.metadata["receipt_id"] == "receipt-call-7"
    assert event.metadata["origin_ids"] == ["asset:report"]
    assert event.metadata["platform_hook"] == "after_tool_call"


def test_skill_and_memory_hooks_map_without_platform_branching() -> None:
    events = (
        _raw_event(
            sequence=1,
            kind=OpenClawEventKind.SKILL_LOAD,
            tool_name=None,
            effect_alias=None,
            receipt_id=None,
            origin_ids=[],
            executed=None,
            action=None,
            source=None,
            sink=None,
            scope=None,
            lifetime=None,
            sensitivity=None,
            policy_fact=None,
            skill_id="summary-reader",
            platform_hook="llm_input",
        ),
        _raw_event(
            sequence=2,
            kind=OpenClawEventKind.MEMORY_READ,
            tool_name="read",
            effect_alias=None,
            receipt_id="receipt-call-2",
            origin_ids=["asset:memory-payload"],
            action=CapabilityAction.MEMORY_READ,
            source="memory:/t12-shared",
            sink="context:/task",
            scope=Scope.EXACT_KEY,
            lifetime=Lifetime.CALL,
            resource="memory:/t12-shared",
            policy_fact="platform_executed_no_grant_fact",
        ),
    )

    translated = translate_openclaw_events(events)

    assert tuple(item.event_type for item in translated) == (
        EventType.SKILL_LOAD,
        EventType.MEMORY_READ,
    )


def test_executed_effect_without_receipt_is_rejected() -> None:
    with pytest.raises(ValidationError, match="receipt"):
        _raw_event(receipt_id=None)


def test_raw_payload_cannot_smuggle_prompt_or_content() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        _raw_event(prompt="secret", content="secret")


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("\n", "第 1 行为空"),
        ("{not-json}\n", "第 1 行无效"),
        (_raw_event(sequence=1).model_dump_json() + "\n", "序号必须从零开始"),
    ],
)
def test_event_file_rejects_blank_invalid_and_non_contiguous_jsonl(
    tmp_path: Path,
    content: str,
    message: str,
) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(OpenClawEventFileError, match=message):
        load_openclaw_events(path)
