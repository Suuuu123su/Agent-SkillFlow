"""从来源混淆原始计数聚合；边界衰减不是来源标签的经验猜测。"""

from skillflow.analysis.provenance_metrics import aggregate_provenance
from skillflow.experiment.t17.v2.analysis_context import AnalysisGroup
from skillflow.experiment.t17.v2.measurements import measure, not_applicable
from skillflow.experiment.t17.v2.statistics_models import Measurement
from skillflow.models.metrics import ProvenanceMetricSet


def provenance_metrics(group: AnalysisGroup) -> dict[str, Measurement]:
    """同协议同模型组内以 Artifact-origin 成员关系为分母。"""
    value = aggregate_provenance(tuple(r.provenance for r in group.runs))
    result = _values(group, value.overall, "provenance.")
    for depth in value.by_boundary_depth:
        prefix = f"provenance.depth_{depth.boundary_depth}."
        result.update(_values(group, depth.metrics, prefix))
        result[prefix + "decay"] = measure(
            depth.decay.numerator,
            depth.decay.denominator,
            group.evidence,
            scope="adjacent_boundary_recall_difference",
            complete=group.complete,
        )
        if depth.decay.denominator == 0 and group.complete:
            result[prefix + "decay"] = not_applicable(
                "没有前一边界或相邻来源召回率没有分母", evidence=group.evidence
            )
    return result


def _values(
    group: AnalysisGroup, value: ProvenanceMetricSet, prefix: str
) -> dict[str, Measurement]:
    result = {
        prefix + name: measure(
            number,
            1,
            group.evidence,
            unit="origin_membership_count",
            scope="artifact_origin_memberships",
            complete=group.complete,
        )
        for name, number in (
            ("tp", value.counts.tp),
            ("fp", value.counts.fp),
            ("fn", value.counts.fn),
        )
    }
    for name, ratio in (("precision", value.precision), ("recall", value.recall), ("f1", value.f1)):
        result[prefix + name] = measure(
            ratio.numerator,
            ratio.denominator,
            group.evidence,
            scope="artifact_origin_memberships",
            complete=group.complete,
        )
    return result
