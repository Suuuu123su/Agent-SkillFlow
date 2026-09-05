import pytest
from pydantic import ValidationError

from skillflow.defense.rx import (
    ORDER,
    RequestEvidence,
    Selection,
    SourceEvidence,
    TaskConstraints,
    TaskPermission,
    evaluate,
    intervene,
    select,
)
from skillflow.models.effects import CapabilityEffect


def request(**changes: object) -> RequestEvidence:
    payload = {
        "request_id": "request-1",
        "actor_id": "worker",
        "session_id": "session-1",
        "effect": {
            "action": "file.read",
            "source": "workspace:/input.txt",
            "sink": "context:/task",
            "scope": "exact-file",
            "lifetime": "call",
            "sensitivity": 1,
        },
        "grant_authorized": True,
        "task_permitted": True,
        "sources": [],
        "provenance_complete": True,
        "authorization_complete": True,
        "evidence_ids": ["request-1"],
        **changes,
    }
    return RequestEvidence.model_validate(payload)


def source(**changes: object) -> SourceEvidence:
    return SourceEvidence.model_validate(
        {
            "artifact_id": "artifact-1",
            "producer_event_id": "event-1",
            "channel": "tool",
            "instruction_authority": False,
            "revoked": False,
            "evidence_ids": ["artifact-1", "event-1"],
            **changes,
        }
    )


@pytest.mark.parametrize(
    "forbidden",
    ["scenario_id", "role", "skill_path", "selector", "gold", "receipt", "hiaa", "future"],
)
def test_rx_online_input_rejects_truth_and_future(forbidden: str) -> None:
    with pytest.raises(ValidationError):
        request(**{forbidden: "hidden"})


def test_no_extra_component_for_clean_request() -> None:
    assert select(request()).components == ()


def test_tool_data_remains_usable_but_cannot_add_authority() -> None:
    current = request(sources=[source()])
    assert select(current).components == ("P",)
    assert evaluate("P", current).action == "allow"
    changed = current.model_copy(update={"task_permitted": False})
    assert evaluate("P", changed).action == "deny"
    assert evaluate("P", changed).artifact_ids == ("artifact-1",)


def test_revocation_targets_only_affected_version_and_preserves_legal_data() -> None:
    revoked = source(channel="memory", revoked=True, memory_key="notes", memory_version_id="v1")
    clean = source(artifact_id="artifact-2", channel="memory", memory_version_id="v2")
    current = request(sources=[revoked, clean])
    assert evaluate("M", current).action == "allow"
    changed = current.model_copy(update={"task_permitted": False})
    result = evaluate("M", changed)
    assert result.action == "deny"
    assert result.artifact_ids == ("artifact-1",)
    assert result.memory_versions == ("v1",)
    assert not clean.revoked


def test_coarse_only_removes_selector_features() -> None:
    current = request(sources=[source(channel="memory", revoked=True)])
    assert select(current).components == ("P", "M")
    assert select(current, coarse=True).components == ()
    assert evaluate("M", current).artifact_ids == ("artifact-1",)


def test_missing_evidence_is_abstention_not_zero_risk() -> None:
    result = select(request(provenance_complete=False))
    assert result.abstain
    assert "EVIDENCE_INCOMPLETE" in result.reasons


def test_all_uses_shared_components_and_stops_at_first_block() -> None:
    current = request(task_permitted=False, sources=[source()])
    selection = Selection(components=ORDER, abstain=False, reasons=(), evidence_ids=())
    results = intervene(selection, current)
    assert len(results) == 1
    assert results[0] == evaluate("T", current)
    assert len(intervene(selection, request())) == 3


def test_task_permission_is_set_membership_not_gold_sequence() -> None:
    current = request()
    other = CapabilityEffect.model_validate(
        {**current.effect.model_dump(), "source": "workspace:/second.txt"}
    )
    task = TaskConstraints(
        contract_id="trusted-task",
        permissions=tuple(
            TaskPermission(
                actor_id="worker",
                session_ids=("session-1", "session-3"),
                effect=e,
                evidence_id="user-task",
            )
            for e in (current.effect, other)
        ),
    )
    for effect in (other, current.effect, other):
        assert task.permits("worker", "session-3", effect)
    assert not task.permits("different", "session-3", other)
