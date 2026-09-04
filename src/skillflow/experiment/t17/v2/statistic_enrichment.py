"""通用计数的簇统计；不把相邻召回率之差错当普通比例相加。"""

from collections.abc import Mapping

from skillflow.experiment.t17.contracts import MeasurementStatus
from skillflow.experiment.t17.v2.measurements import contrast_interval
from skillflow.experiment.t17.v2.statistics_models import (
    ClusterTerm,
    Measurement,
    StatisticalInterval,
)

NONADDITIVE = {
    "unique_canonical_effect_keys",
    "observed_reachable_unauthorized_effect_set_difference",
}


def enrich_statistics(
    values: dict[str, Measurement], clusters: Mapping[str, dict[str, Measurement]]
) -> dict[str, Measurement]:
    """从每个表述簇的原始计数生成可重用的充分统计，不平均百分比。"""
    result = dict(values)
    for name, value in values.items():
        if value.status is not MeasurementStatus.MEASURED or value.cluster_terms:
            continue
        if value.denominator_scope in NONADDITIVE:
            interval = StatisticalInterval(
                status=MeasurementStatus.NOT_APPLICABLE,
                method="cluster_bootstrap",
                reason="预注册的去重可达集合指标只作描述性集合计数，不按频次加权",
                complete_clusters=len(clusters),
            )
            result[name] = value.model_copy(
                update={"intervals": (interval,), "complete_clusters": len(clusters)}
            )
            continue
        if value.denominator_scope == "adjacent_boundary_recall_difference":
            terms, signs = _decay_terms(name, clusters)
        else:
            terms, signs = _ordinary_terms(name, value, clusters), {"value": 1}
        result[name] = contrast_interval(value, terms, signs)
    return result


def _ordinary_terms(
    name: str, value: Measurement, clusters: Mapping[str, dict[str, Measurement]]
) -> tuple[ClusterTerm, ...]:
    total = (
        value.unit not in {"ratio", "signed_contrast", "milliseconds"}
        or value.denominator_scope == "core_and_replay_observed_usage"
    )
    result = []
    for cluster, vector in clusters.items():
        item = vector.get(name)
        if item is None or item.numerator is None or item.denominator is None:
            continue
        denominator = 1 / len(clusters) if total else float(item.denominator)
        result.append(
            ClusterTerm(
                cluster=cluster,
                term="value",
                numerator=float(item.numerator),
                denominator=denominator,
            )
        )
    return tuple(result)


def _decay_terms(
    name: str, clusters: Mapping[str, dict[str, Measurement]]
) -> tuple[tuple[ClusterTerm, ...], dict[str, int]]:
    depth = int(name.split(".")[1].removeprefix("depth_"))
    rows = []
    for cluster, vector in clusters.items():
        for term, boundary in (("previous", depth - 1), ("current", depth)):
            value = vector.get(f"provenance.depth_{boundary}.recall")
            if value is not None and value.numerator is not None and value.denominator is not None:
                rows.append(
                    ClusterTerm(
                        cluster=cluster,
                        term=term,
                        numerator=float(value.numerator),
                        denominator=float(value.denominator),
                    )
                )
    return tuple(rows), {"previous": 1, "current": -1}
