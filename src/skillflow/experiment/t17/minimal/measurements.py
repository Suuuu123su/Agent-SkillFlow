"""不依赖 Scenario ID 的测量构造和精确比例差。"""

from fractions import Fraction

from skillflow.experiment.t17.contracts import MeasurementStatus
from skillflow.experiment.t17.minimal.report_models import MinimalMeasurement
from skillflow.models.metrics import MetricStatus, RatioMetric, SignedRatioMetric


def measured(
    numerator: float,
    denominator: float,
    evidence: tuple[str, ...],
    *,
    unit: str = "ratio",
    scope: str = "scheduled_core",
) -> MinimalMeasurement:
    """零值必须有完整负例证据；无分母则明确设计不适用。"""
    if denominator == 0:
        return not_applicable("设计中没有符合分母条件的单元", unit=unit, scope=scope)
    return MinimalMeasurement(
        status=MeasurementStatus.MEASURED,
        numerator=numerator,
        denominator=denominator,
        value=numerator / denominator,
        unit=unit,
        denominator_scope=scope,
        evidence_ids=tuple(dict.fromkeys(evidence)),
    )


def not_applicable(
    reason: str, *, unit: str = "ratio", scope: str = "design"
) -> MinimalMeasurement:
    """N/A 不携带伪造的 0/0。"""
    return MinimalMeasurement(
        status=MeasurementStatus.NOT_APPLICABLE, reason=reason, unit=unit, denominator_scope=scope
    )


def from_ratio(
    ratio: RatioMetric | SignedRatioMetric,
    *,
    scope: str,
    reason: str = "设计中无适用分母",
) -> MinimalMeasurement:
    """旧统计合同只转换状态，不改原始计数或证据。"""
    if ratio.status is MetricStatus.NOT_APPLICABLE:
        return not_applicable(reason, scope=scope)
    return measured(ratio.numerator, ratio.denominator, ratio.evidence_ids, scope=scope)


def signed_difference(
    positive: tuple[tuple[int, int], ...],
    negative: tuple[tuple[int, int], ...],
    evidence: tuple[str, ...],
    *,
    scope: str,
) -> MinimalMeasurement:
    """HIAA/成对差保留精确有符号分子，不假造统一 Trial 分母。"""
    if any(denominator == 0 for _, denominator in (*positive, *negative)):
        return not_applicable("差值所需设计单元没有有效观察", scope=scope)
    difference = sum((Fraction(n, d) for n, d in positive), Fraction()) - sum(
        (Fraction(n, d) for n, d in negative),
        Fraction(),
    )
    return measured(
        difference.numerator, difference.denominator, evidence, unit="signed_contrast", scope=scope
    )
