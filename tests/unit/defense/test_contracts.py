import pytest
from pydantic import ValidationError

from skillflow.defense.models import AttackDiagnosis, AttackSignalVector, DefensePlan
from skillflow.defense.router import EvidenceDefenseRouter


def signal(**changes: object) -> AttackSignalVector:
    data: dict[str, object] = {
        "run_id": "r1",
        "session_id": "s1",
        "request_event_id": "e1",
        "grant_missing": False,
        "scope_mismatch": False,
        "lifetime_mismatch": False,
        "revoked_origin": False,
        "untrusted_context_in_basis": False,
        "untrusted_tool_return_in_basis": False,
        "cross_session_memory_path": False,
        "authorization_claim_in_basis": False,
        "candidate_influence": False,
        "confirmed_influence": False,
        "target_effect_requested": True,
        "target_effect_executed": False,
        "receipt_present": False,
        "sink_severity": 1,
        "evidence_availability": {"authorization": True, "provenance": True},
        "evidence_ids": ["e1"],
        "signal_evidence": {},
    }
    data.update(changes)
    return AttackSignalVector.model_validate(data)


@pytest.mark.parametrize("field", ["scenario_id", "attack_family", "source_path", "golden"])
def test_signals_reject_labels(field: str) -> None:
    with pytest.raises(ValidationError):
        signal(**{field: "attack"})


def test_empty_diagnosis_is_not_fake_certainty() -> None:
    diagnosis, plan = EvidenceDefenseRouter().route(signal())
    assert diagnosis.mechanisms == ()
    assert not diagnosis.abstain
    assert plan.selected_defense_ids == ()
    assert plan.action == "allow"
    assert AttackDiagnosis.model_validate_json(diagnosis.model_dump_json()) == diagnosis
    assert DefensePlan.model_validate_json(plan.model_dump_json()) == plan


@pytest.mark.parametrize(
    ("changes", "mechanisms", "defenses"),
    [
        ({"grant_missing": True}, {"privilege"}, {"task-alignment", "drift-isolation"}),
        ({"scope_mismatch": True}, {"privilege"}, {"task-alignment", "drift-isolation"}),
        ({"lifetime_mismatch": True}, {"privilege"}, {"task-alignment", "drift-isolation"}),
        ({"untrusted_context_in_basis": True}, {"context-tool"}, {"tdg"}),
        (
            {"untrusted_tool_return_in_basis": True, "sink_severity": 4},
            {"context-tool"},
            {"tdg", "causal"},
        ),
        (
            {"cross_session_memory_path": True, "sink_severity": 4},
            {"memory"},
            {"drift-isolation", "causal"},
        ),
        ({"revoked_origin": True}, {"memory"}, {"drift-isolation"}),
        (
            {"authorization_claim_in_basis": True, "grant_missing": True},
            {"authorization", "privilege"},
            {"task-alignment", "drift-isolation"},
        ),
    ],
)
def test_router_uses_evidence_not_labels(
    changes: dict[str, object], mechanisms: set[str], defenses: set[str]
) -> None:
    diagnosis, plan = EvidenceDefenseRouter().route(signal(**changes))
    assert set(diagnosis.mechanisms) == mechanisms
    assert set(plan.selected_defense_ids) == defenses
    assert set(plan.evidence_ids) <= {"e1"}


def test_missing_critical_evidence_abstains() -> None:
    diagnosis, plan = EvidenceDefenseRouter().route(
        signal(evidence_availability={"authorization": False, "provenance": True}, sink_severity=4)
    )
    assert diagnosis.abstain
    assert diagnosis.confidence == "low"
    assert diagnosis.missing_evidence == ("authorization",)
    assert plan.action == "confirm"


def test_mixed_rules_are_minimal_union() -> None:
    diagnosis, plan = EvidenceDefenseRouter().route(
        signal(
            grant_missing=True,
            cross_session_memory_path=True,
            untrusted_context_in_basis=True,
            sink_severity=4,
        )
    )
    assert set(diagnosis.mechanisms) == {"privilege", "memory", "context-tool"}
    assert set(plan.selected_defense_ids) == {"task-alignment", "tdg", "drift-isolation", "causal"}
    assert len(plan.selected_defense_ids) == 4
