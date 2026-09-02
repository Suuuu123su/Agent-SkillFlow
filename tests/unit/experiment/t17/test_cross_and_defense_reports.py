from skillflow.experiment.t17.comparison_models import T17Direction
from skillflow.experiment.t17.contracts import MeasurementStatus
from skillflow.experiment.t17.cross_model_report import _direction_comparison
from skillflow.experiment.t17.defense_report import _gain
from skillflow.experiment.t17.metric_models import (
    T17IntervalEstimate,
    T17IntervalMethod,
)


def _interval(
    point: float,
    lower: float,
    upper: float,
) -> T17IntervalEstimate:
    return T17IntervalEstimate(
        status=MeasurementStatus.MEASURED,
        method=T17IntervalMethod.CLUSTER_BOOTSTRAP,
        point=point,
        lower=lower,
        upper=upper,
        resamples=10_000,
        seed=17_017,
    )


def test_cross_zero_interval_is_indeterminate_not_robust_agreement() -> None:
    comparison = _direction_comparison(
        "hiaa:c1",
        "model1",
        _interval(0.2, -0.1, 0.4),
        "model2",
        _interval(0.3, 0.1, 0.5),
    )

    assert comparison.point_direction_agreement is True
    assert comparison.model1.interval_direction is T17Direction.INDETERMINATE
    assert comparison.model2.interval_direction is T17Direction.POSITIVE
    assert comparison.robust_direction_agreement is False


def test_security_gain_is_monitor_minus_enforce_without_weighted_score() -> None:
    gain = _gain("risk_vte_rate", 0.75, 0.25)

    assert gain.status is MeasurementStatus.MEASURED
    assert gain.security_gain == 0.5
