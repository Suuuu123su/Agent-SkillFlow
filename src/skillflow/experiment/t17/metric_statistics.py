"""T17 scheduled 比例、Wilson 描述区间与固定 cluster bootstrap。"""

import math
import random
from dataclasses import dataclass

from skillflow.experiment.t17.contracts import (
    MeasurementStatus,
    RatioMeasurement,
)
from skillflow.experiment.t17.metric_models import (
    T17IntervalEstimate,
    T17IntervalMethod,
)

WILSON_Z_95 = 1.959963984540054
BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_SEED = 17_017
MIN_BOOTSTRAP_CLUSTERS = 2


@dataclass(frozen=True, slots=True)
class ScheduledRatioContext:
    """scheduled 比例的证据和非数值状态说明。"""

    evidence_ids: tuple[str, ...] = ()
    incomplete_reason: str = "scheduled 分母尚未完整观察"
    not_applicable_reason: str = "实验设计没有适用单元"


class T17MetricNarrowingError(ValueError):
    """measured Ratio 没有通过类型窄化。"""

    def __str__(self) -> str:
        """返回稳定 reason code。"""
        return "t17_measured_ratio_narrowing"


DEFAULT_SCHEDULED_RATIO_CONTEXT = ScheduledRatioContext()


def scheduled_ratio(
    numerator: int,
    observed: int,
    scheduled: int,
    context: ScheduledRatioContext = DEFAULT_SCHEDULED_RATIO_CONTEXT,
) -> RatioMeasurement:
    """完整时发布 scheduled 比例，未完成时只保留 observed/scheduled。"""
    if scheduled == 0:
        return RatioMeasurement(
            status=MeasurementStatus.NOT_APPLICABLE,
            reason=context.not_applicable_reason,
        )
    if observed < scheduled:
        return RatioMeasurement(
            status=MeasurementStatus.INCOMPLETE,
            numerator=numerator,
            denominator=observed,
            scheduled_denominator=scheduled,
            reason=context.incomplete_reason,
            evidence_ids=context.evidence_ids,
        )
    return RatioMeasurement(
        status=MeasurementStatus.MEASURED,
        numerator=numerator,
        denominator=scheduled,
        scheduled_denominator=scheduled,
        value=numerator / scheduled,
        evidence_ids=context.evidence_ids,
    )


def wilson_interval(measurement: RatioMeasurement) -> T17IntervalEstimate:
    """为完整链级比例生成明确标注的描述性 Wilson 95% 区间。"""
    if measurement.status is not MeasurementStatus.MEASURED:
        return T17IntervalEstimate(
            status=measurement.status,
            method=T17IntervalMethod.WILSON_CHAIN_DESCRIPTIVE,
            reason=measurement.reason or "比例尚未 measured",
            evidence_ids=measurement.evidence_ids,
        )
    _numerator, denominator, point = _narrow_measured_ratio(measurement)
    z2 = WILSON_Z_95**2
    scale = 1 + (z2 / denominator)
    center = (point + (z2 / (2 * denominator))) / scale
    radius = (
        WILSON_Z_95
        * math.sqrt((point * (1 - point) / denominator) + (z2 / (4 * denominator**2)))
        / scale
    )
    return T17IntervalEstimate(
        status=MeasurementStatus.MEASURED,
        method=T17IntervalMethod.WILSON_CHAIN_DESCRIPTIVE,
        point=point,
        lower=max(0.0, center - radius),
        upper=min(1.0, center + radius),
        evidence_ids=measurement.evidence_ids,
    )


def cluster_bootstrap_interval(
    cluster_values: tuple[float, ...],
    *,
    point: float | None = None,
    evidence_ids: tuple[str, ...] = (),
) -> T17IntervalEstimate:
    """对 semantic template cluster 均值执行固定 10,000 次 bootstrap。"""
    if len(cluster_values) < MIN_BOOTSTRAP_CLUSTERS:
        return T17IntervalEstimate(
            status=MeasurementStatus.NOT_APPLICABLE,
            method=T17IntervalMethod.CLUSTER_BOOTSTRAP,
            reason="少于两个 semantic template cluster，区间不适用",
            evidence_ids=evidence_ids,
        )
    generator = random.Random(BOOTSTRAP_SEED)  # noqa: S311 - statistical bootstrap
    size = len(cluster_values)
    samples = sorted(
        sum(generator.choice(cluster_values) for _ in range(size)) / size
        for _ in range(BOOTSTRAP_RESAMPLES)
    )
    estimate = sum(cluster_values) / size if point is None else point
    lower = _percentile(samples, 0.025)
    upper = _percentile(samples, 0.975)
    return T17IntervalEstimate(
        status=MeasurementStatus.MEASURED,
        method=T17IntervalMethod.CLUSTER_BOOTSTRAP,
        point=estimate,
        lower=min(lower, estimate),
        upper=max(upper, estimate),
        resamples=BOOTSTRAP_RESAMPLES,
        seed=BOOTSTRAP_SEED,
        evidence_ids=evidence_ids,
    )


def percentile(values: tuple[float, ...], probability: float) -> float | None:
    """返回线性插值百分位；空序列保持 N/A。"""
    if not values:
        return None
    return _percentile(sorted(values), probability)


def _percentile(sorted_values: list[float] | tuple[float, ...], probability: float) -> float:
    position = (len(sorted_values) - 1) * probability
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return sorted_values[lower_index]
    weight = position - lower_index
    return sorted_values[lower_index] * (1 - weight) + sorted_values[upper_index] * weight


def _narrow_measured_ratio(
    measurement: RatioMeasurement,
) -> tuple[int, int, float]:
    numerator = measurement.numerator
    denominator = measurement.denominator
    point = measurement.value
    if numerator is None or denominator is None or point is None:
        raise T17MetricNarrowingError
    return numerator, denominator, point
