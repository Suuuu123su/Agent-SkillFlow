import pytest

from skillflow.experiment.t18.hiaa import HiaaTrial, compute_hiaa
from skillflow.experiment.t18.matrix import build_matrix


def trials() -> tuple[HiaaTrial, ...]:
    matrix = build_matrix("fake_reference")
    values = []
    for group in matrix.hiaa_groups:
        for name, trial_id in group.cells.items():
            values.append(
                HiaaTrial(
                    domain="fake_reference",
                    trial_id=trial_id,
                    run_id="run:" + trial_id,
                    complete=True,
                    valid=True,
                    target_effect=name == "p11" and group.mode == "monitor",
                    evidence_ids=("receipt-or-terminal:" + trial_id,),
                    refusal=False,
                    no_call=False,
                    schema_failure=False,
                    task_failure=False,
                )
            )
    return tuple(values)


def test_hiaa_uses_four_cell_counts_and_monitor_delta() -> None:
    reports = compute_hiaa(build_matrix("fake_reference"), trials())
    assert len(reports) == 4
    for report in reports:
        assert report.status == "measured"
        assert report.scheduled.value == (1 if report.mode == "monitor" else 0)
        assert report.valid_only.value == report.scheduled.value
        assert report.delta_hiaa.value == (0 if report.mode == "monitor" else 1)
        assert all(
            c.scheduled.denominator == 1 and c.valid_only.denominator == 1
            for c in report.cells.values()
        )


def test_missing_or_invalid_cell_is_incomplete_never_not_applicable() -> None:
    matrix = build_matrix("fake_reference")
    samples = trials()
    missing = compute_hiaa(matrix, samples[1:])[0]
    assert missing.status == "incomplete"
    assert missing.scheduled.value is None
    bad = samples[0].model_copy(update={"valid": False, "no_call": True, "task_failure": True})
    invalid = compute_hiaa(matrix, (bad, *samples[1:]))[0]
    assert invalid.scheduled.status == "measured"
    assert invalid.valid_only.status == "incomplete"
    assert invalid.valid_only.value is None
    assert invalid.cells["p00"].failures["no_call"] == 1
    assert invalid.cells["p00"].failures["task_failure"] == 1


def test_duplicate_run_and_unknown_cell_are_not_counted() -> None:
    matrix = build_matrix("fake_reference")
    samples = trials()
    with pytest.raises(ValueError, match="duplicate"):
        compute_hiaa(matrix, (*samples, samples[0]))
    with pytest.raises(ValueError, match="unknown"):
        compute_hiaa(
            matrix,
            (*samples, samples[0].model_copy(update={"trial_id": "outside", "run_id": "extra"})),
        )
