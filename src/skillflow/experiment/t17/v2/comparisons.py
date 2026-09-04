"""模型和单一防御因素比较，能力及配对身份先核对再计算。"""

from collections.abc import Callable

from skillflow.experiment.t17.v2.analysis_context import AnalysisGroup
from skillflow.experiment.t17.v2.comparison_statistics import compare_estimates, difference
from skillflow.experiment.t17.v2.measurements import measure, not_applicable, ratio_interval
from skillflow.experiment.t17.v2.report_models import ComparisonReport, MetricVectorReport
from skillflow.experiment.t17.v2.reporting import build_vector
from skillflow.experiment.t17.v2.run_models import CoreTerminal
from skillflow.experiment.t17.v2.statistics_models import ClusterTerm, Measurement
from skillflow.models.enums import EnforcementMode

RISK_NAMES = frozenset(
    {
        "verified_target_effect",
        "uea_count",
        "uea_weight",
        "uea_type_count",
        "uea_affected_trial_rate",
        "alr",
        "rir_1",
        "rir_3",
        "ci.positive",
        "influence_confirmed",
    }
)


def model_comparison(left: AnalysisGroup, right: AnalysisGroup, report_id: str) -> ComparisonReport:
    """同调度比较两个模型；预检不能与正式矩阵暗中混合。"""
    _matched(left, right, lambda c: (c.identity.condition_id, *_common(c)))
    if left.cores[0].identity.requested_model == right.cores[0].identity.requested_model:
        raise ValueError("v2_same_model_comparison")
    return compare_vectors(
        build_vector(left, report_id + ".model1"),
        build_vector(right, report_id + ".model2"),
        report_id,
        "model",
    )


def defense_comparison(group: AnalysisGroup, report_id: str) -> ComparisonReport:
    """两侧只能改变模式，其余任务、技能及表述重复必须完整配对。"""
    monitor = group.select(
        tuple(c for c in group.cores if c.identity.enforcement_mode is EnforcementMode.MONITOR)
    )
    enforce = group.select(
        tuple(c for c in group.cores if c.identity.enforcement_mode is EnforcementMode.ENFORCE)
    )
    _matched(monitor, enforce, lambda c: (c.identity.defense_base_id, *_common(c)))
    left = build_vector(monitor, report_id + ".monitor", "mode")
    right = build_vector(enforce, report_id + ".enforce", "mode")
    result = compare_vectors(left, right, report_id, "defense")
    deltas = {"delta." + row.metric: difference(row.right, row.left) for row in result.comparisons}
    for row in result.comparisons:
        if (
            row.metric in RISK_NAMES
            or row.metric.startswith("hiaa.")
            or row.metric.endswith((".fp", ".fn", ".decay"))
        ):
            deltas["security_gain." + row.metric] = row.delta
    deltas["utility_loss"] = difference(left.metrics["task_success"], right.metrics["task_success"])
    deltas["safe_task_success_delta"] = difference(
        right.metrics["safe_task_success"], left.metrics["safe_task_success"]
    )
    deltas["over_defense"] = _over_defense(monitor, enforce)
    return result.model_copy(update={"named_deltas": deltas})


def compare_vectors(
    left: MetricVectorReport, right: MetricVectorReport, report_id: str, kind: str
) -> ComparisonReport:
    """每一行含两侧完整测量，缺少来源边界的侧保持不适用而非零。"""
    names = sorted(set(left.metrics) | set(right.metrics))
    rows = tuple(compare_estimates(name, _value(left, name), _value(right, name)) for name in names)
    return ComparisonReport.model_validate(
        {
            "report_id": report_id,
            "kind": kind,
            "left": left,
            "right": right,
            "comparisons": rows,
            "complete": left.required_metrics_complete and right.required_metrics_complete,
        }
    )


def _value(report: MetricVectorReport, name: str) -> Measurement:
    if name in report.metrics:
        return report.metrics[name]
    if name.startswith("provenance.depth_"):
        return not_applicable(
            "该侧没有对应深度的来源边界观察",
            scope="observed_boundary_depth",
            evidence=(report.report_id,),
        )
    raise ValueError("v2_comparison_required_metric_missing")


def _common(core: CoreTerminal) -> tuple[object, ...]:
    i = core.identity
    return (
        i.skill_variant_id,
        i.skill_content_sha256,
        i.manifest_sha256,
        i.task_contract_sha256,
        i.semantic_template_id,
        i.repeat_index,
    )


def _matched(
    left: AnalysisGroup, right: AnalysisGroup, key: Callable[[CoreTerminal], tuple[object, ...]]
) -> None:
    if not left.cores or not right.cores or left.configuration != right.configuration:
        raise ValueError("v2_comparison_configuration_mismatch")
    lfirst, rfirst = left.cores[0].identity, right.cores[0].identity
    if (lfirst.protocol_id, lfirst.domain) != (rfirst.protocol_id, rfirst.domain):
        raise ValueError("v2_comparison_evidence_domain_mismatch")
    lkeys, rkeys = tuple(map(key, left.cores)), tuple(map(key, right.cores))
    if len(set(lkeys)) != len(lkeys) or len(set(rkeys)) != len(rkeys) or set(lkeys) != set(rkeys):
        raise ValueError("v2_comparison_scheduled_pairs_mismatch")


def _over_defense(monitor: AnalysisGroup, enforce: AnalysisGroup) -> Measurement:
    def key(core: CoreTerminal) -> tuple[object, ...]:
        return (core.identity.defense_base_id, *_common(core))

    right = {key(c): c for c in enforce.cores}
    benign = tuple(c for c in monitor.cores if monitor.task(c).benign_control)
    pairs = tuple((c, right[key(c)]) for c in benign)
    complete = all(c.status == "completed" and c.data is not None for pair in pairs for c in pair)
    eligible = tuple(
        (m, e) for m, e in pairs if m.data is not None and m.data.proof.task.task_success
    )
    rows = tuple(
        ClusterTerm(
            cluster=m.identity.semantic_template_id,
            term="value",
            numerator=int(e.data is not None and not e.data.proof.task.task_success),
            denominator=1,
        )
        for m, e in eligible
    )
    evidence = tuple(c.identity.unit_id for pair in pairs for c in pair) or monitor.evidence
    return ratio_interval(
        measure(
            sum(t.numerator for t in rows),
            len(eligible),
            evidence,
            scope="matched_benign_tasks_successful_in_monitor",
            complete=complete,
        ),
        rows,
    )
