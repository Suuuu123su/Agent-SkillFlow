"""高级指标共享的结构化比例构造。"""

from skillflow.models.metrics import MetricStatus, RatioMetric


def ratio_metric(
    numerator: int,
    denominator: int,
    evidence_ids: tuple[str, ...],
) -> RatioMetric:
    """把零分母统一编码为结构化 N/A。"""
    if denominator == 0:
        return RatioMetric(
            numerator=0,
            denominator=0,
            value=None,
            status=MetricStatus.NOT_APPLICABLE,
            evidence_ids=evidence_ids,
        )
    return RatioMetric(
        numerator=numerator,
        denominator=denominator,
        value=numerator / denominator,
        status=MetricStatus.DEFINED,
        evidence_ids=evidence_ids,
    )
