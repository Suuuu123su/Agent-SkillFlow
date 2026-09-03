"""单域来源混淆计数、PRF 与逐边界深度 Decay。"""

from skillflow.analysis.provenance_metrics import aggregate_provenance
from skillflow.experiment.t17.minimal.measurements import from_ratio, measured
from skillflow.experiment.t17.minimal.report_models import MinimalMeasurement
from skillflow.models.metrics import ProvenanceMetricSet, ProvenanceMetricSummary


def provenance_metrics(
    summaries: tuple[ProvenanceMetricSummary, ...],
) -> dict[str, MinimalMeasurement]:
    """只合并调用方已核验的一个执行域，不合并模型/版本。"""
    combined = aggregate_provenance(summaries)
    result = _metrics(combined.overall, "provenance.")
    for depth in combined.by_boundary_depth:
        prefix = f"provenance.depth_{depth.boundary_depth}."
        result.update(_metrics(depth.metrics, prefix))
        result[prefix + "decay"] = from_ratio(
            depth.decay,
            scope="adjacent_boundary_recall_difference",
            reason="不存在前一边界深度，或相邻 Recall 无适用分母",
        )
    return result


def _metrics(value: ProvenanceMetricSet, prefix: str) -> dict[str, MinimalMeasurement]:
    counts = value.counts
    result = {
        prefix + label: measured(
            count,
            1,
            counts.artifact_ids,
            unit="origin_membership_count",
            scope="domain_artifact_origin_pairs",
        )
        for label, count in (("tp", counts.tp), ("fp", counts.fp), ("fn", counts.fn))
    }
    result.update(
        {
            prefix + label: from_ratio(ratio, scope="domain_artifact_origin_pairs")
            for label, ratio in (
                ("precision", value.precision),
                ("recall", value.recall),
                ("f1", value.f1),
            )
        }
    )
    return result
