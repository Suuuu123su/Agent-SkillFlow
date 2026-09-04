"""跨模型与防御比较的符号、分母和配对重抽样反例。"""

from skillflow.experiment.t17.contracts import MeasurementStatus
from skillflow.experiment.t17.v2.comparison_statistics import compare_estimates
from skillflow.experiment.t17.v2.measurements import measure, not_applicable, ratio_interval
from skillflow.experiment.t17.v2.statistics_models import ClusterTerm


def test_cross_zero_intervals_are_not_direction_agreement() -> None:
    terms = (
        ClusterTerm(cluster="s1", term="value", numerator=0, denominator=1),
        ClusterTerm(cluster="s2", term="value", numerator=1, denominator=1),
    )
    value = ratio_interval(measure(1, 2, ("trial-a", "trial-b")), terms)
    compared = compare_estimates("risk", value, value)
    assert compared.point_agreement == "agreement"
    assert compared.interval_agreement == "indeterminate"
    assert compared.delta.value == 0
    assert compared.delta.intervals[0].lower == 0
    assert compared.delta.intervals[0].upper == 0
    assert compared.delta.complete_clusters == 2


def test_missing_measurement_is_not_zero_or_agreement() -> None:
    left = measure(1, 2, ("trial-a",))
    result = compare_estimates("risk", left, not_applicable("没有该实验设计"))
    assert result.delta.status is MeasurementStatus.NOT_APPLICABLE
    assert result.delta.value is None
    assert result.point_agreement == "indeterminate"


def test_unknown_side_preserves_incomplete_status() -> None:
    result = compare_estimates("risk", measure(1, 2, ("a",)), measure(0, 2, ("b",), complete=False))
    assert result.delta.status is MeasurementStatus.INCOMPLETE
    assert result.delta.value is None
