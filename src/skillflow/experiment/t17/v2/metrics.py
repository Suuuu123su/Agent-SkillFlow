"""第二版单模型测量向量，指标计算不按场景或攻击标签赋值。"""

from skillflow.experiment.t17.v2.analysis_context import AnalysisGroup
from skillflow.experiment.t17.v2.authorization_metrics import authorization_metrics
from skillflow.experiment.t17.v2.causal_metrics import causal_metrics
from skillflow.experiment.t17.v2.core_metrics import core_metrics
from skillflow.experiment.t17.v2.efficiency_metrics import efficiency_metrics
from skillflow.experiment.t17.v2.hiaa_metrics import hiaa_metrics
from skillflow.experiment.t17.v2.paired_metrics import paired_metrics
from skillflow.experiment.t17.v2.provenance_metrics import provenance_metrics
from skillflow.experiment.t17.v2.statistic_enrichment import enrich_statistics
from skillflow.experiment.t17.v2.statistics_models import Measurement


def metric_vector(group: AnalysisGroup) -> dict[str, Measurement]:
    """统一构造完整向量，模块间不得用相同名字覆盖不同统计。"""
    clusters = {
        identifier: _raw_vector(
            group.select(
                tuple(c for c in group.cores if c.identity.semantic_template_id == identifier)
            )
        )
        for identifier in sorted({c.identity.semantic_template_id for c in group.cores})
    }
    return enrich_statistics(_raw_vector(group), clusters)


def _raw_vector(group: AnalysisGroup) -> dict[str, Measurement]:
    result: dict[str, Measurement] = {}
    for calculate in (
        core_metrics,
        provenance_metrics,
        causal_metrics,
        authorization_metrics,
        hiaa_metrics,
        paired_metrics,
        efficiency_metrics,
    ):
        values = calculate(group)
        if set(result) & set(values):
            raise ValueError("v2_metric_identifier_collision")
        result.update(values)
    return result
