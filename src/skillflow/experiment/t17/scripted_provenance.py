"""T17-D 来源 TP/FP/FN、P/R/F1 与逐深度 Decay micro 聚合。"""

from collections import defaultdict
from dataclasses import dataclass

from skillflow.experiment.t17.contracts import MeasurementStatus, RatioMeasurement
from skillflow.experiment.t17.scripted_models import (
    ProvenanceAggregateSummary,
    ProvenanceDepthSummary,
)
from skillflow.models.reports import RunRiskReport


@dataclass(frozen=True, slots=True)
class _Counts:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    def add(self, tp: int, fp: int, fn: int) -> "_Counts":
        return _Counts(self.tp + tp, self.fp + fp, self.fn + fn)


def aggregate_scripted_provenance(
    runs: tuple[RunRiskReport, ...],
) -> ProvenanceAggregateSummary:
    """先汇总原始计数，再计算 overall 与逐边界比例。"""
    overall = _Counts()
    by_depth: dict[int, _Counts] = defaultdict(_Counts)
    evidence: list[str] = []
    for run in runs:
        run_counts = run.provenance.overall.counts
        overall = overall.add(run_counts.tp, run_counts.fp, run_counts.fn)
        evidence.extend(run_counts.artifact_ids)
        for depth_metrics in run.provenance.by_boundary_depth:
            item = depth_metrics.metrics.counts
            by_depth[depth_metrics.boundary_depth] = by_depth[depth_metrics.boundary_depth].add(
                item.tp,
                item.fp,
                item.fn,
            )
    ordered = tuple(sorted(by_depth))
    recalls = {
        depth: _ratio(by_depth[depth].tp, by_depth[depth].tp + by_depth[depth].fn)
        for depth in ordered
    }
    depth_summaries = []
    for index, boundary_depth in enumerate(ordered):
        boundary_counts = by_depth[boundary_depth]
        next_depth = None if index + 1 == len(ordered) else ordered[index + 1]
        current_recall = recalls[boundary_depth].value
        next_recall = None if next_depth is None else recalls[next_depth].value
        decay = (
            None if current_recall is None or next_recall is None else current_recall - next_recall
        )
        depth_summaries.append(
            ProvenanceDepthSummary(
                boundary_depth=boundary_depth,
                tp=boundary_counts.tp,
                fp=boundary_counts.fp,
                fn=boundary_counts.fn,
                precision=_ratio(
                    boundary_counts.tp,
                    boundary_counts.tp + boundary_counts.fp,
                ),
                recall=recalls[boundary_depth],
                f1=_ratio(
                    2 * boundary_counts.tp,
                    (2 * boundary_counts.tp) + boundary_counts.fp + boundary_counts.fn,
                ),
                decay_status=(
                    MeasurementStatus.NOT_APPLICABLE
                    if decay is None
                    else MeasurementStatus.MEASURED
                ),
                decay_value=decay,
            )
        )
    evidence_ids = tuple(dict.fromkeys(evidence))
    return ProvenanceAggregateSummary(
        tp=overall.tp,
        fp=overall.fp,
        fn=overall.fn,
        precision=_ratio(overall.tp, overall.tp + overall.fp, evidence_ids),
        recall=_ratio(overall.tp, overall.tp + overall.fn, evidence_ids),
        f1=_ratio(
            2 * overall.tp,
            (2 * overall.tp) + overall.fp + overall.fn,
            evidence_ids,
        ),
        by_boundary_depth=tuple(depth_summaries),
    )


def _ratio(
    numerator: int,
    denominator: int,
    evidence_ids: tuple[str, ...] = (),
) -> RatioMeasurement:
    if denominator == 0:
        return RatioMeasurement(
            status=MeasurementStatus.NOT_APPLICABLE,
            reason="来源比例分母为 0",
        )
    return RatioMeasurement(
        status=MeasurementStatus.MEASURED,
        numerator=numerator,
        denominator=denominator,
        scheduled_denominator=denominator,
        value=numerator / denominator,
        evidence_ids=evidence_ids,
    )
