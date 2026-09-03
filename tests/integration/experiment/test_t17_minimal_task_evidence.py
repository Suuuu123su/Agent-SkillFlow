from dataclasses import replace
from pathlib import Path

import pytest

from skillflow.benchmark.runner import ScenarioRunner
from skillflow.benchmark.t12_fixtures import t12_fixture_registry
from skillflow.experiment.t17.minimal.configuration import build_minimal_configuration
from skillflow.experiment.t17.minimal.task_evidence import evaluate_normal_task
from skillflow.store.sqlite_store import SqliteEventStore


@pytest.mark.parametrize(
    ("scenario_id", "expected_task", "expected_safe"),
    [
        ("B0", True, True),
        ("B1", True, False),
        ("C1", True, False),
        ("N0", True, True),
        ("S1", False, False),
        ("S1_CONTROL", True, True),
        ("L1", False, False),
        ("L1_CONTROL", True, True),
        ("M2", True, False),
    ],
)
def test_normal_task_uses_trusted_artifact_receipt_resource_and_session(
    tmp_path: Path,
    scenario_id: str,
    expected_task: bool,
    expected_safe: bool,
) -> None:
    contract = next(
        item
        for item in build_minimal_configuration(Path()).tasks
        if item.scenario_id == scenario_id
    )
    result = ScenarioRunner(*t12_fixture_registry()).run(
        Path(contract.scenario_path),
        tmp_path / "run",
        "normal-task-v2",
    )
    with SqliteEventStore(result.database_path) as store:
        evidence = evaluate_normal_task(result, contract, store)
    assert evidence.evaluator_version == "2.0.0"
    assert evidence.task_success is expected_task
    assert evidence.safe_task_success is expected_safe
    assert evidence.evidence_ids
    assert evidence.legacy_task_success is result.risk_report.task_success
    document = evidence.model_dump(mode="json")
    document["task_success"] = not expected_task
    with pytest.raises(ValueError, match="task_success"):
        type(evidence).model_validate(document)


def test_task_evidence_rejects_missing_receipt_and_foreign_run(tmp_path: Path) -> None:
    contract = build_minimal_configuration(Path()).tasks[0]
    result = ScenarioRunner(*t12_fixture_registry()).run(
        Path(contract.scenario_path),
        tmp_path / "run",
        "bindings",
    )
    with SqliteEventStore(result.database_path) as store:
        with pytest.raises(ValueError, match="receipt"):
            evaluate_normal_task(replace(result, receipts=()), contract, store)
        with pytest.raises(ValueError, match="run"):
            evaluate_normal_task(replace(result, run_id="foreign-run"), contract, store)
        missing = evaluate_normal_task(replace(result, artifact_ids_by_alias={}), contract, store)
    assert missing.task_success is False
    assert missing.artifacts[0].present is False
    assert missing.status.value == "measured"
