from pathlib import Path

from skillflow.experiment.t17.contracts import MeasurementStatus
from skillflow.experiment.t17.v2.fake_client import V2FakeClient
from skillflow.experiment.t19.core_metrics import core_metrics
from skillflow.experiment.t19.execution import CoreRecord, ExecutionSetup, execute
from skillflow.experiment.t19.hiaa import hiaa_metrics
from skillflow.experiment.t19.matrix import formal, precheck
from skillflow.experiment.t19.tasks import task_variant

ROOT = Path(__file__).resolve().parents[3]


def test_missing_scheduled_core_is_incomplete_not_a_zero(tmp_path: Path) -> None:
    trials = precheck()[:2]
    trial = trials[0]
    record, _ = execute(
        ExecutionSetup(ROOT, tmp_path, trial.trial_id, "fake_reference", trial.group),
        task_variant(ROOT, trial.mechanism, trial.role, trial.template),
        V2FakeClient(),
    )
    metrics = core_metrics(trials, (record,))
    assert metrics["task_success"].status is MeasurementStatus.INCOMPLETE
    assert metrics["task_success"].value is None
    assert metrics["task_success"].denominator == 2
    assert metrics["core_evidence_coverage"].value == 0.5


def test_evidence_references_are_bound_to_exported_facts(tmp_path: Path) -> None:
    trial = next(t for t in precheck() if t.mechanism == "C2" and t.group == "Evidence")
    record, _ = execute(
        ExecutionSetup(ROOT, tmp_path, trial.trial_id, "fake_reference", trial.group),
        task_variant(ROOT, trial.mechanism, trial.role, trial.template),
        V2FakeClient(),
    )
    metrics = core_metrics((trial,), (record,))
    assert metrics["diagnosis.evidence_reference_validity"].value == 1
    assert metrics["uea_operations"].value == 0
    assert metrics["safe_task_success"].value == 1


def test_hiaa_requires_all_four_cells_and_preserves_zero_contrast(tmp_path: Path) -> None:
    trials = tuple(
        t
        for t in formal()
        if t.mechanism == "C1"
        and t.group == "Monitor"
        and t.template == "heldout-ledger"
        and t.repeat == 1
    )
    records: list[CoreRecord] = []
    for trial in trials:
        record, _ = execute(
            ExecutionSetup(
                ROOT, tmp_path, trial.trial_id, "fake_reference", trial.group, bridge=trial.bridge
            ),
            task_variant(ROOT, trial.mechanism, trial.role, trial.template),
            V2FakeClient(),
        )
        records.append(record)
    result = hiaa_metrics(trials, tuple(records))
    key = "Monitor/C1/heldout-ledger/scheduled/hiaa"
    assert result[key].status is MeasurementStatus.MEASURED
    assert result[key].value == 0
    missing = hiaa_metrics(trials, tuple(records[:-1]))
    assert missing[key].status is MeasurementStatus.INCOMPLETE
    assert missing[key].value is None
