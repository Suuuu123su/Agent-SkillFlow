from pathlib import Path

import pytest
from pydantic import ValidationError

from skillflow.defense.models import AttackDiagnosis, DefenseOutcome, DefensePlan
from skillflow.experiment.t18.dataset import DatasetManifest, FileDigest, _check_manifest
from skillflow.experiment.t18.hiaa import CellRate, Contrast, HiaaTrial
from tests.unit.defense.test_contracts import signal


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"evidence_ids": ["e1", "e1"]}, "duplicate_evidence"),
        ({"signal_evidence": {"grant": ["foreign"]}}, "not_bound"),
        ({"confirmed_influence": True}, "requires_candidate"),
        ({"target_effect_executed": True}, "requires_receipt"),
    ],
)
def test_signal_binding_rejects_forged_facts(changes: dict[str, object], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        signal(**changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"mechanisms": ["privilege", "privilege"]},
        {"abstain": True},
        {"abstain": True, "missing_evidence": ["authorization"], "confidence": "high"},
    ],
)
def test_diagnosis_rejects_duplicate_or_false_confidence(changes: dict[str, object]) -> None:
    payload = {
        "diagnosis_id": "d1",
        "mechanisms": [],
        "confidence": "high",
        "abstain": False,
        "evidence_ids": ["e1"],
        "missing_evidence": [],
        **changes,
    }
    with pytest.raises(ValidationError):
        AttackDiagnosis.model_validate(payload)


def test_plan_rejects_duplicate_defenses() -> None:
    with pytest.raises(ValidationError, match="duplicate_defense"):
        DefensePlan(
            plan_id="p1",
            selected_defense_ids=("causal", "causal"),
            action="deny",
            evidence_ids=("e1",),
            selection_reason_codes=("CAUSAL",),
            estimated_extra_steps=2,
        )


def test_outcome_keeps_authorization_and_safe_success_distinct() -> None:
    outcome = DefenseOutcome(
        outcome_id="pair",
        before_run_id="r1",
        after_run_id="r2",
        before_effect_ids=("eff-1",),
        after_effect_ids=("eff-2",),
        before_authorization=(False,),
        after_authorization=(False,),
        task_success=True,
        safe_task_success=False,
        utility_loss=0,
        over_defense=False,
        residual_risk=True,
        actual_extra_steps=1,
        actual_latency_ms=0,
        evidence_ids=("r1", "r2"),
    )
    assert DefenseOutcome.model_validate_json(outcome.model_dump_json()) == outcome
    for change in ({"after_authorization": []}, {"safe_task_success": True}):
        with pytest.raises(ValidationError):
            DefenseOutcome.model_validate({**outcome.model_dump(), **change})


@pytest.mark.parametrize("path", ["../outside.json", "."])
def test_dataset_manifest_rejects_escape_before_reading(path: str, tmp_path: Path) -> None:
    manifest = DatasetManifest(
        domain="scripted",
        core_count=0,
        replay_count=0,
        files={path: FileDigest(sha256="0" * 64, bytes=0)},
    )
    with pytest.raises(ValueError, match="path_escape"):
        _check_manifest(tmp_path, manifest)


@pytest.mark.parametrize(
    "changes",
    [
        {"complete": False},
        {"refusal": True},
        {"evidence_ids": []},
    ],
)
def test_hiaa_validity_needs_complete_failure_free_evidence(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        HiaaTrial.model_validate(
            {
                "trial_id": "t1",
                "domain": "scripted",
                "run_id": "r1",
                "complete": True,
                "valid": True,
                "target_effect": False,
                "evidence_ids": ["r1"],
                "refusal": False,
                "no_call": False,
                "schema_failure": False,
                "task_failure": False,
                **changes,
            }
        )


def test_hiaa_counts_and_incomplete_values_are_closed() -> None:
    for changes in ({"numerator": 2}, {"value": 0.5}, {"status": "incomplete"}):
        with pytest.raises(ValidationError):
            CellRate.model_validate(
                {
                    "status": "measured",
                    "numerator": 1,
                    "denominator": 1,
                    "value": 1,
                    "evidence_ids": ["r1"],
                    **changes,
                }
            )
    with pytest.raises(ValidationError, match="contrast_status"):
        Contrast(status="incomplete", value=0, evidence_ids=())
