import pytest
from pydantic import ValidationError

from skillflow.experiment.t17.contracts import MeasurementStatus
from skillflow.experiment.t17.minimal.measurements import (
    from_ratio,
    measured,
    not_applicable,
    signed_difference,
)
from skillflow.experiment.t17.minimal.report_models import MinimalMeasurement
from skillflow.models.metrics import MetricStatus, RatioMetric


@pytest.mark.parametrize(
    "changed",
    [
        {"numerator": None},
        {"denominator": None},
        {"value": None},
        {"denominator": 0},
        {"denominator": -1},
        {"evidence_ids": ()},
        {"value": 0.7},
        {"numerator": float("nan")},
        {"denominator": float("inf")},
    ],
)
def test_measured_rejects_missing_or_inconsistent_evidence(changed: dict[str, object]) -> None:
    document = measured(1, 2, ("run-a",)).model_dump()
    with pytest.raises(ValidationError):
        MinimalMeasurement.model_validate({**document, **changed})


@pytest.mark.parametrize("status", ["not_applicable", "not_available"])
def test_na_is_not_zero_and_requires_reason(status: str) -> None:
    document = {
        "status": status,
        "unit": "ratio",
        "denominator_scope": "design",
        "reason": "design",
    }
    assert MinimalMeasurement.model_validate(document).value is None
    for changes in (
        {"numerator": 0},
        {"denominator": 0},
        {"value": 0},
        {"reason": None},
        {"scheduled_denominator": 23},
    ):
        with pytest.raises(ValidationError):
            MinimalMeasurement.model_validate({**document, **changes})


def test_incomplete_never_publishes_a_point_estimate() -> None:
    result = MinimalMeasurement(
        status=MeasurementStatus.INCOMPLETE,
        numerator=1,
        denominator=2,
        scheduled_denominator=23,
        reason="partial",
        unit="ratio",
        denominator_scope="scheduled",
    )
    assert result.value is None
    for changes in ({"value": 0}, {"reason": None}, {"scheduled_denominator": None}):
        with pytest.raises(ValidationError):
            MinimalMeasurement.model_validate({**result.model_dump(), **changes})


def test_signed_contrasts_keep_exact_denominators_and_negative_values() -> None:
    result = signed_difference(((1, 3),), ((1, 2),), ("paired-a",), scope="pair")
    assert (result.numerator, result.denominator, result.value) == (-1, 6, -1 / 6)
    assert (
        signed_difference(((0, 0),), (), ("pair",), scope="pair").status
        is MeasurementStatus.NOT_APPLICABLE
    )
    assert measured(0, 0, ()).status is MeasurementStatus.NOT_APPLICABLE
    assert not_applicable("one_cluster").numerator is None
    ratio = RatioMetric(
        numerator=1, denominator=2, value=0.5, status=MetricStatus.DEFINED, evidence_ids=("run",)
    )
    assert from_ratio(ratio, scope="sample").value == 0.5
    empty = RatioMetric(numerator=0, denominator=0, value=None, status=MetricStatus.NOT_APPLICABLE)
    assert from_ratio(empty, scope="sample").reason is not None
