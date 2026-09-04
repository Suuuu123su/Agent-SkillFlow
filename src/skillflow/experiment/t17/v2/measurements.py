"""第二版测量构造器，按证据完整性而不是结果好坏决定状态。"""

from skillflow.experiment.t17.contracts import MeasurementStatus
from skillflow.experiment.t17.v2.statistics import cluster_contrast, wilson_interval
from skillflow.experiment.t17.v2.statistics_models import ClusterTerm, Measurement


def measure(  # noqa: PLR0913 -- 三项证据与三个显式测量属性共同构成固定合同。
    numerator: float,
    denominator: float,
    evidence: tuple[str, ...],
    *,
    unit: str = "ratio",
    scope: str = "scheduled_core",
    complete: bool = True,
) -> Measurement:
    """完整的零值仍为实测；未运行不进入零值，零分母明确不适用。"""
    ids = tuple(dict.fromkeys(evidence))
    if not complete:
        return Measurement(
            status=MeasurementStatus.INCOMPLETE,
            numerator=numerator,
            denominator=denominator,
            scheduled_denominator=int(denominator),
            unit=unit,
            denominator_scope=scope,
            evidence_ids=ids,
            reason="预定单元中存在未运行、未终态或绑定失败；不把缺失补成零",
        )
    if denominator == 0:
        return not_applicable("设计中没有符合分母的观察", scope=scope, evidence=ids, unit=unit)
    return Measurement(
        status=MeasurementStatus.MEASURED,
        numerator=numerator,
        denominator=denominator,
        value=numerator / denominator,
        unit=unit,
        denominator_scope=scope,
        evidence_ids=ids,
    )


def not_applicable(
    reason: str, *, scope: str = "design", evidence: tuple[str, ...] = (), unit: str = "ratio"
) -> Measurement:
    """没有相应设计或合格分母，不代表平台缺少观测能力。"""
    return Measurement(
        status=MeasurementStatus.NOT_APPLICABLE,
        reason=reason,
        unit=unit,
        denominator_scope=scope,
        evidence_ids=evidence,
    )


def ratio_interval(value: Measurement, rows: tuple[ClusterTerm, ...]) -> Measurement:
    """比例提供描述性 Wilson 与适用的簇区间，非测量值不加假区间。"""
    if (
        value.status is not MeasurementStatus.MEASURED
        or value.numerator is None
        or value.denominator is None
    ):
        return value
    bootstrap = cluster_contrast(rows, {"value": 1})
    intervals = (wilson_interval(int(value.numerator), int(value.denominator)), bootstrap)
    return value.model_copy(
        update={
            "intervals": intervals,
            "complete_clusters": bootstrap.complete_clusters,
            "cluster_terms": rows,
            "contrast_signs": {"value": 1},
        }
    )


def contrast_interval(
    value: Measurement, rows: tuple[ClusterTerm, ...], signs: dict[str, int]
) -> Measurement:
    """有符号差值只使用共同簇的成对重抽样区间。"""
    if value.status is not MeasurementStatus.MEASURED:
        return value
    interval = cluster_contrast(rows, signs)
    return value.model_copy(
        update={
            "intervals": (interval,),
            "complete_clusters": interval.complete_clusters,
            "cluster_terms": rows,
            "contrast_signs": signs,
        }
    )
