from pathlib import Path

import pytest
from pydantic import ValidationError

from skillflow.experiment.t17.contracts import HookName
from skillflow.experiment.t17.minimal.configuration import build_minimal_configuration
from skillflow.experiment.t17.minimal.contracts import MinimalConfiguration, NormalTaskContract
from skillflow.experiment.t17.minimal.task_models import (
    ArtifactCheck,
    EffectCheck,
    NormalTaskEvidence,
)


@pytest.fixture(scope="module")
def configuration() -> MinimalConfiguration:
    return build_minimal_configuration(Path())


@pytest.mark.parametrize("mutation", ["artifact", "effect", "hook"])
def test_task_contract_rejects_duplicate_assertions_and_missing_hook(
    configuration: MinimalConfiguration, mutation: str
) -> None:
    task = next(item for item in configuration.tasks if item.scenario_id == "B0")
    document = task.model_dump()
    if mutation == "artifact":
        document["artifacts"] = (*task.artifacts, *task.artifacts)
    elif mutation == "effect":
        document["effects"] = (*task.effects, *task.effects)
    else:
        document["required_hooks"] = tuple(
            item for item in task.required_hooks if item is not HookName.TASK_SUCCESS
        )
    with pytest.raises(ValidationError):
        NormalTaskContract.model_validate(document)


@pytest.mark.parametrize(
    "mutation",
    [
        "repeat",
        "golden",
        "defense",
        "path",
        "duplicate_task",
        "pair",
        "selection",
        "replay_duplicate",
        "unknown",
    ],
)
def test_configuration_rejects_unfrozen_schedules(
    configuration: MinimalConfiguration, mutation: str
) -> None:
    document = configuration.model_dump(mode="json")
    if mutation == "repeat":
        document["matrix"]["determinism_repeats"] = 2
    elif mutation == "golden":
        document["golden"] = document["golden"][:-1]
    elif mutation == "defense":
        document["defense_pairs"] = [["missing", "b0-monitor"]]
    elif mutation == "path":
        document["tasks"][0]["scenario_path"] = "scenarios/missing.yaml"
    elif mutation == "duplicate_task":
        document["tasks"][1]["scenario_id"] = document["tasks"][0]["scenario_id"]
    elif mutation == "pair":
        document["equivalent_task_pairs"] = [["missing", "B0"]]
    elif mutation == "selection":
        document["replay_variants"] = document["replay_variants"][:-1]
    elif mutation == "replay_duplicate":
        document["replay_variants"].append(document["replay_variants"][0])
    else:
        document["replay_variants"].append("missing")
        document["replay_pairs_by_variant"]["missing"] = 1
    with pytest.raises(ValidationError):
        MinimalConfiguration.model_validate(document)


@pytest.fixture
def evidence(configuration: MinimalConfiguration) -> NormalTaskEvidence:
    task = next(item for item in configuration.tasks if item.scenario_id == "B0")
    artifact = ArtifactCheck(
        requirement=task.artifacts[0],
        present=True,
        artifact_id="artifact-a",
        actual_sha256=task.artifacts[0].expected_sha256,
        session_id=task.artifacts[0].session_id,
        event_id="event-a",
        satisfied=True,
    )
    effect = EffectCheck(
        requirement=task.effects[0],
        effect_ids=("effect-a",),
        receipt_ids=("receipt-a",),
        session_ids=(task.effects[0].session_id,),
        satisfied=True,
    )
    return NormalTaskEvidence(
        run_id="unit-only",
        scenario_id="B0",
        task_contract_sha256="a" * 64,
        artifacts=(artifact,),
        effects=(effect,),
        completed_session_ids=(task.artifacts[0].session_id,),
        risk_effect_ids=(),
        risk_receipt_ids=(),
        task_success=True,
        safe_task_success=True,
        legacy_task_success=None,
        evidence_ids=("event-a", "receipt-a"),
    )


@pytest.mark.parametrize("mutation", ["missing_field", "wrong_commitment"])
def test_artifact_check_requires_commitment_and_binding(
    evidence: NormalTaskEvidence, mutation: str
) -> None:
    document = evidence.artifacts[0].model_dump()
    document["artifact_id" if mutation == "missing_field" else "actual_sha256"] = (
        None if mutation == "missing_field" else "f" * 64
    )
    with pytest.raises(ValidationError):
        ArtifactCheck.model_validate(document)


@pytest.mark.parametrize("mutation", ["alignment", "duplicate", "session", "satisfied"])
def test_effect_check_requires_unique_receipts_and_session(
    evidence: NormalTaskEvidence, mutation: str
) -> None:
    document = evidence.effects[0].model_dump()
    if mutation == "alignment":
        document["receipt_ids"] = ()
    elif mutation == "duplicate":
        document.update(
            effect_ids=("effect-a", "effect-a"),
            receipt_ids=("receipt-a", "receipt-b"),
            session_ids=("session-0", "session-0"),
        )
    elif mutation == "session":
        document["session_ids"] = ("wrong-session",)
    else:
        document["satisfied"] = False
    with pytest.raises(ValidationError):
        EffectCheck.model_validate(document)


@pytest.mark.parametrize(
    "changes",
    [
        {"task_success": False},
        {"risk_effect_ids": ("effect-a",)},
        {
            "risk_effect_ids": ("effect-a", "effect-a"),
            "risk_receipt_ids": ("receipt-a", "receipt-b"),
        },
        {"safe_task_success": False},
        {"completed_session_ids": ("missing",)},
    ],
)
def test_normal_task_evidence_rejects_false_conjunctions(
    evidence: NormalTaskEvidence, changes: dict[str, object]
) -> None:
    with pytest.raises(ValidationError):
        NormalTaskEvidence.model_validate({**evidence.model_dump(), **changes})
