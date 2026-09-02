"""从两个完整 Formal Phase 报告生成不 pooled 的跨模型比较。"""

from pathlib import Path

from skillflow.experiment.io import sha256_file, write_json_model
from skillflow.experiment.t17.comparison_models import (
    T17CrossModelReport,
    T17Direction,
    T17DirectionComparison,
    T17RatioSideBySide,
    T17SignedModelEstimate,
)
from skillflow.experiment.t17.contracts import (
    MeasurementStatus,
    RatioMeasurement,
)
from skillflow.experiment.t17.metric_models import (
    T17IntervalEstimate,
    T17PhaseMetricsReport,
)
from skillflow.experiment.t17.metric_statistics import (
    ScheduledRatioContext,
    scheduled_ratio,
)


def build_cross_model_report(
    model1_path: Path,
    model2_path: Path,
) -> T17CrossModelReport:
    """比较相同指标点/区间方向，同时保留两个独立分母。"""
    model1 = T17PhaseMetricsReport.model_validate_json(model1_path.read_text(encoding="utf-8"))
    model2 = T17PhaseMetricsReport.model_validate_json(model2_path.read_text(encoding="utf-8"))
    ratios = tuple(
        T17RatioSideBySide(metric=name, model1=left, model2=right)
        for name, left, right in _ratio_pairs(model1, model2)
    )
    shared_intervals = tuple(
        sorted(set(model1.bootstrap_intervals) & set(model2.bootstrap_intervals))
    )
    directions = tuple(
        _direction_comparison(
            name,
            model1.evidence_domain.model_revision or "",
            model1.bootstrap_intervals[name],
            model2.evidence_domain.model_revision or "",
            model2.bootstrap_intervals[name],
        )
        for name in shared_intervals
    )
    point_evidence = tuple(item.metric for item in directions)
    robust_candidates = tuple(
        item
        for item in directions
        if item.model1.interval_direction is not T17Direction.INDETERMINATE
        and item.model2.interval_direction is not T17Direction.INDETERMINATE
    )
    complete = (
        model1.required_metrics_complete
        and model2.required_metrics_complete
        and bool(directions)
        and all(
            item.model1.interval.status is MeasurementStatus.MEASURED
            and item.model2.interval.status is MeasurementStatus.MEASURED
            for item in directions
        )
    )
    return T17CrossModelReport(
        report_id="t17-cross-model-formal-v1",
        model1_domain=model1.evidence_domain,
        model2_domain=model2.evidence_domain,
        source_phase_sha256={
            "model1": sha256_file(model1_path),
            "model2": sha256_file(model2_path),
        },
        side_by_side_ratios=ratios,
        signed_directions=directions,
        point_direction_agreement=scheduled_ratio(
            sum(item.point_direction_agreement for item in directions),
            len(directions),
            len(directions),
            ScheduledRatioContext(evidence_ids=point_evidence),
        ),
        robust_direction_agreement=scheduled_ratio(
            sum(item.robust_direction_agreement for item in robust_candidates),
            len(robust_candidates),
            len(robust_candidates),
            ScheduledRatioContext(
                evidence_ids=tuple(item.metric for item in robust_candidates),
                not_applicable_reason=("两个模型的区间方向均为 indeterminate"),
            ),
        ),
        complete=complete,
    )


def write_cross_model_report(
    model1_path: Path,
    model2_path: Path,
    output_path: Path,
) -> T17CrossModelReport:
    """不可覆盖写出跨模型比较。"""
    report = build_cross_model_report(model1_path, model2_path)
    write_json_model(output_path, report)
    return report


def _ratio_pairs(
    model1: T17PhaseMetricsReport,
    model2: T17PhaseMetricsReport,
) -> tuple[tuple[str, RatioMeasurement, RatioMeasurement], ...]:
    return (
        ("task_success_rate", model1.task_success_rate, model2.task_success_rate),
        (
            "safe_task_success_rate",
            model1.safe_task_success_rate,
            model2.safe_task_success_rate,
        ),
        (
            "benign_refusal_rate",
            model1.benign_refusal_rate,
            model2.benign_refusal_rate,
        ),
        (
            "verified_target_effect_rate",
            model1.verified_target_effect_rate,
            model2.verified_target_effect_rate,
        ),
        (
            "uea_affected_trial_rate",
            model1.uea.affected_trial_rate,
            model2.uea.affected_trial_rate,
        ),
        (
            "replay_nonzero_rate",
            model1.causal_impact.nonzero_rate,
            model2.causal_impact.nonzero_rate,
        ),
    )


def _direction_comparison(
    metric: str,
    model1_revision: str,
    model1_interval: T17IntervalEstimate,
    model2_revision: str,
    model2_interval: T17IntervalEstimate,
) -> T17DirectionComparison:
    model1 = T17SignedModelEstimate(
        model_revision=model1_revision,
        interval=model1_interval,
        point_direction=_point_direction(model1_interval.point),
        interval_direction=_interval_direction(
            model1_interval.lower,
            model1_interval.upper,
        ),
    )
    model2 = T17SignedModelEstimate(
        model_revision=model2_revision,
        interval=model2_interval,
        point_direction=_point_direction(model2_interval.point),
        interval_direction=_interval_direction(
            model2_interval.lower,
            model2_interval.upper,
        ),
    )
    return T17DirectionComparison(
        metric=metric,
        model1=model1,
        model2=model2,
        point_direction_agreement=(model1.point_direction is model2.point_direction),
        robust_direction_agreement=(
            model1.interval_direction is model2.interval_direction
            and model1.interval_direction is not T17Direction.INDETERMINATE
        ),
    )


def _point_direction(value: float | None) -> T17Direction:
    if value is None:
        return T17Direction.INDETERMINATE
    if value < 0:
        return T17Direction.NEGATIVE
    if value > 0:
        return T17Direction.POSITIVE
    return T17Direction.ZERO


def _interval_direction(
    lower: float | None,
    upper: float | None,
) -> T17Direction:
    if lower is None or upper is None:
        return T17Direction.INDETERMINATE
    if upper < 0:
        return T17Direction.NEGATIVE
    if lower > 0:
        return T17Direction.POSITIVE
    return T17Direction.INDETERMINATE
