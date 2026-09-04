"""严格区分点值方向、区间方向与同簇配对差。"""

from skillflow.experiment.t17.contracts import MeasurementStatus
from skillflow.experiment.t17.v2.measurements import contrast_interval, measure
from skillflow.experiment.t17.v2.report_models import Agreement, Direction, MetricComparison
from skillflow.experiment.t17.v2.statistics_models import Measurement, StatisticalInterval


def compare_estimates(metric: str, left: Measurement, right: Measurement) -> MetricComparison:
    """区间含零一律不确定，两个相同点值只算描述性同向。"""
    lp, rp = point_direction(left.value), point_direction(right.value)
    li, ri = interval_direction(left), interval_direction(right)
    return MetricComparison(
        metric=metric,
        left=left,
        right=right,
        delta=difference(left, right),
        left_point_direction=lp,
        right_point_direction=rp,
        left_interval_direction=li,
        right_interval_direction=ri,
        point_agreement=_agreement(lp, rp),
        interval_agreement=_agreement(li, ri),
    )


def difference(left: Measurement, right: Measurement) -> Measurement:
    """同一簇权重同时作用两侧充分统计；不以独立区间相减冒充配对区间。"""
    evidence = tuple(dict.fromkeys((*left.evidence_ids, *right.evidence_ids)))
    if (
        left.status is not MeasurementStatus.MEASURED
        or right.status is not MeasurementStatus.MEASURED
    ):
        statuses = {left.status, right.status}
        status = next(
            s
            for s in (
                MeasurementStatus.INCOMPLETE,
                MeasurementStatus.NOT_AVAILABLE,
                MeasurementStatus.NOT_APPLICABLE,
            )
            if s in statuses
        )
        return Measurement(
            status=status,
            scheduled_denominator=max(
                left.scheduled_denominator or 0, right.scheduled_denominator or 0
            )
            if status is MeasurementStatus.INCOMPLETE
            else None,
            unit="signed_contrast",
            denominator_scope="left_minus_right",
            evidence_ids=evidence,
            reason="至少一侧没有完整适用测量；差值不补零",
        )
    if left.value is None or right.value is None:
        raise ValueError("v2_measured_comparison_value_missing")
    value = measure(
        left.value - right.value, 1, evidence, unit="signed_contrast", scope="left_minus_right"
    )
    if not left.cluster_terms or not right.cluster_terms:
        interval = StatisticalInterval(
            status=MeasurementStatus.NOT_APPLICABLE,
            method="cluster_bootstrap",
            reason="至少一侧为预注册描述性集合计数，无配对抽样区间",
            complete_clusters=min(left.complete_clusters, right.complete_clusters),
        )
        return value.model_copy(
            update={"intervals": (interval,), "complete_clusters": interval.complete_clusters}
        )
    terms = tuple(
        t.model_copy(update={"term": side + "." + t.term})
        for side, measurement in (("left", left), ("right", right))
        for t in measurement.cluster_terms
    )
    signs = {
        side + "." + term: coefficient * sign
        for side, measurement, coefficient in (("left", left, 1), ("right", right, -1))
        for term, sign in measurement.contrast_signs.items()
    }
    return contrast_interval(value, terms, signs)


def point_direction(value: float | None) -> Direction:
    """点值零与缺失严格区分。"""
    if value is None:
        return "indeterminate"
    if value > 0:
        return "positive"
    return "negative" if value < 0 else "zero"


def interval_direction(value: Measurement) -> Direction:
    """只使用簇重抽样区间判断推断方向，描述性 Wilson 不替代。"""
    interval = next((i for i in value.intervals if i.method == "cluster_bootstrap"), None)
    if (
        interval is None
        or interval.status is not MeasurementStatus.MEASURED
        or interval.lower is None
        or interval.upper is None
    ):
        return "indeterminate"
    if interval.lower > 0:
        return "positive"
    return "negative" if interval.upper < 0 else "indeterminate"


def _agreement(left: Direction, right: Direction) -> Agreement:
    if "indeterminate" in {left, right}:
        return "indeterminate"
    return "agreement" if left == right else "disagreement"
