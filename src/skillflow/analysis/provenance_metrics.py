"""来源 Precision、Recall、F1 与边界深度 Decay 计算。"""

from dataclasses import dataclass

from skillflow.analysis.errors import AnalysisInvariantError
from skillflow.analysis.facts import ProvenanceSample
from skillflow.models.metrics import (
    MetricStatus,
    ProvenanceCounts,
    ProvenanceDepthMetrics,
    ProvenanceMetricSet,
    ProvenanceMetricSummary,
    RatioMetric,
    SignedRatioMetric,
)


def calculate_provenance(
    samples: tuple[ProvenanceSample, ...],
) -> ProvenanceMetricSummary:
    """按 Artifact 对齐来源集合并输出总体和逐深度指标。"""
    unique_samples: dict[str, ProvenanceSample] = {}
    for sample in samples:
        if sample.boundary_depth < 0:
            raise AnalysisInvariantError(
                "calculate_provenance",
                f"boundary_depth 不能为负：{sample.artifact_id}",
            )
        previous = unique_samples.get(sample.artifact_id)
        if previous is not None and (
            previous.boundary_depth != sample.boundary_depth
            or previous.observed_origins != sample.observed_origins
            or previous.oracle_origins != sample.oracle_origins
        ):
            raise AnalysisInvariantError(
                "calculate_provenance",
                f"同一 Artifact 出现冲突来源事实：{sample.artifact_id}",
            )
        if previous is None:
            unique_samples[sample.artifact_id] = sample
        else:
            unique_samples[sample.artifact_id] = ProvenanceSample(
                artifact_id=sample.artifact_id,
                boundary_depth=sample.boundary_depth,
                observed_origins=sample.observed_origins,
                oracle_origins=sample.oracle_origins,
                evidence_event_ids=_unique(
                    (*previous.evidence_event_ids, *sample.evidence_event_ids)
                ),
            )

    deduplicated = tuple(unique_samples.values())
    by_depth_samples: dict[int, list[ProvenanceSample]] = {}
    for sample in deduplicated:
        by_depth_samples.setdefault(sample.boundary_depth, []).append(sample)
    metric_by_depth = {
        depth: _metric_set(tuple(depth_samples))
        for depth, depth_samples in sorted(by_depth_samples.items())
    }
    by_depth = tuple(
        ProvenanceDepthMetrics(
            boundary_depth=depth,
            metrics=metrics,
            decay=_decay(metric_by_depth.get(depth - 1), metrics),
        )
        for depth, metrics in metric_by_depth.items()
    )
    return ProvenanceMetricSummary(
        overall=_metric_set(deduplicated),
        by_boundary_depth=by_depth,
    )


def aggregate_provenance(
    summaries: tuple[ProvenanceMetricSummary, ...],
) -> ProvenanceMetricSummary:
    """汇总原始 TP/FP/FN 与 Artifact 实例，重新计算 micro 比例。"""
    overall = _combine_metric_sets(tuple(summary.overall for summary in summaries))
    sets_by_depth: dict[int, list[ProvenanceMetricSet]] = {}
    for summary in summaries:
        for item in summary.by_boundary_depth:
            sets_by_depth.setdefault(item.boundary_depth, []).append(item.metrics)
    metric_by_depth = {
        depth: _combine_metric_sets(tuple(metric_sets))
        for depth, metric_sets in sorted(sets_by_depth.items())
    }
    by_depth = tuple(
        ProvenanceDepthMetrics(
            boundary_depth=depth,
            metrics=metrics,
            decay=_decay(metric_by_depth.get(depth - 1), metrics),
        )
        for depth, metrics in metric_by_depth.items()
    )
    return ProvenanceMetricSummary(
        overall=overall,
        by_boundary_depth=by_depth,
    )


@dataclass(frozen=True, slots=True)
class _MetricTotals:
    tp: int
    fp: int
    fn: int
    artifact_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]


def _metric_set(samples: tuple[ProvenanceSample, ...]) -> ProvenanceMetricSet:
    return _metric_from_totals(
        _MetricTotals(
            tp=sum(len(sample.observed_origins & sample.oracle_origins) for sample in samples),
            fp=sum(len(sample.observed_origins - sample.oracle_origins) for sample in samples),
            fn=sum(len(sample.oracle_origins - sample.observed_origins) for sample in samples),
            artifact_ids=tuple(sample.artifact_id for sample in samples),
            evidence_ids=_unique(
                tuple(
                    evidence_id
                    for sample in samples
                    for evidence_id in (sample.artifact_id, *sample.evidence_event_ids)
                )
            ),
        )
    )


def _combine_metric_sets(
    metric_sets: tuple[ProvenanceMetricSet, ...],
) -> ProvenanceMetricSet:
    return _metric_from_totals(
        _MetricTotals(
            tp=sum(item.counts.tp for item in metric_sets),
            fp=sum(item.counts.fp for item in metric_sets),
            fn=sum(item.counts.fn for item in metric_sets),
            artifact_ids=tuple(
                artifact_id for item in metric_sets for artifact_id in item.counts.artifact_ids
            ),
            evidence_ids=_unique(
                tuple(
                    evidence_id
                    for item in metric_sets
                    for metric in (item.precision, item.recall, item.f1)
                    for evidence_id in metric.evidence_ids
                )
            ),
        )
    )


def _metric_from_totals(totals: _MetricTotals) -> ProvenanceMetricSet:
    return ProvenanceMetricSet(
        counts=ProvenanceCounts(
            tp=totals.tp,
            fp=totals.fp,
            fn=totals.fn,
            artifact_ids=totals.artifact_ids,
        ),
        precision=_ratio(totals.tp, totals.tp + totals.fp, totals.evidence_ids),
        recall=_ratio(totals.tp, totals.tp + totals.fn, totals.evidence_ids),
        f1=_ratio(
            2 * totals.tp,
            2 * totals.tp + totals.fp + totals.fn,
            totals.evidence_ids,
        ),
    )


def _ratio(numerator: int, denominator: int, evidence_ids: tuple[str, ...]) -> RatioMetric:
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


def _decay(
    previous: ProvenanceMetricSet | None,
    current: ProvenanceMetricSet,
) -> SignedRatioMetric:
    previous_recall = previous.recall if previous is not None else None
    if (
        previous_recall is None
        or previous_recall.denominator == 0
        or current.recall.denominator == 0
    ):
        return SignedRatioMetric(
            numerator=0,
            denominator=0,
            value=None,
            status=MetricStatus.NOT_APPLICABLE,
            evidence_ids=current.recall.evidence_ids,
        )
    numerator = (
        previous_recall.numerator * current.recall.denominator
        - current.recall.numerator * previous_recall.denominator
    )
    denominator = previous_recall.denominator * current.recall.denominator
    return SignedRatioMetric(
        numerator=numerator,
        denominator=denominator,
        value=numerator / denominator,
        status=MetricStatus.DEFINED,
        evidence_ids=_unique((*previous_recall.evidence_ids, *current.recall.evidence_ids)),
    )


def _unique(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))
