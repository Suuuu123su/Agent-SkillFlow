"""生成分层完整指标向量，公开每个比较的两个独立分母。"""

from skillflow.experiment.t17.contracts import MeasurementStatus
from skillflow.experiment.t17.v2.analysis_context import AnalysisGroup
from skillflow.experiment.t17.v2.metrics import metric_vector
from skillflow.experiment.t17.v2.report_models import MetricVectorReport, StratumIdentity


def build_vector(group: AnalysisGroup, report_id: str, kind: str = "stage") -> MetricVectorReport:
    """不存在空总体；没有模型、条件或模式混淆的隐式微平均。"""
    if not group.cores:
        raise ValueError("v2_empty_report_group")
    identities = tuple(c.identity for c in group.cores)
    first = identities[0]
    values = metric_vector(group)
    return MetricVectorReport.model_validate(
        {
            "report_id": report_id,
            "kind": kind,
            "identity": StratumIdentity(
                protocol_id=first.protocol_id,
                domain=first.domain,
                requested_model=first.requested_model,
                model_revision=first.model_revision,
                stages=tuple(sorted({i.stage for i in identities})),
                condition_ids=tuple(sorted({i.condition_id for i in identities})),
                skill_variant_ids=tuple(sorted({i.skill_variant_id for i in identities})),
                enforcement_modes=tuple(sorted({i.enforcement_mode for i in identities})),
                phase_contract_sha256=tuple(sorted({i.phase_contract_sha256 for i in identities})),
                matrix_sha256=tuple(sorted({i.matrix_sha256 for i in identities})),
                skill_content_sha256={
                    i.skill_variant_id: i.skill_content_sha256 for i in identities
                },
                manifest_sha256={i.skill_variant_id: i.manifest_sha256 for i in identities},
                raw_manifest_sha256=group.raw_manifest_sha256,
            ),
            "scheduled_core": len(group.cores),
            "scheduled_replay": len(group.replays),
            "metrics": values,
            "required_metrics_complete": group.complete
            and group.replay_complete
            and all(
                v.status in {MeasurementStatus.MEASURED, MeasurementStatus.NOT_APPLICABLE}
                for v in values.values()
            ),
        }
    )


def condition_vectors(group: AnalysisGroup, prefix: str) -> tuple[MetricVectorReport, ...]:
    """每个条件单独给出分子、分母和适用区间，不丢弃失败任务。"""
    return tuple(
        build_vector(
            group.select(tuple(c for c in group.cores if c.identity.condition_id == name)),
            prefix + "." + name,
            "condition",
        )
        for name in sorted({c.identity.condition_id for c in group.cores})
    )
