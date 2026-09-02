"""从一个 T17 Live Attempt 机械生成完整 Phase 指标报告。"""

import json
from dataclasses import dataclass
from pathlib import Path

from skillflow.experiment.aggregation import (
    StandardAggregationInput,
    aggregate_standard_results,
)
from skillflow.experiment.io import write_json_model
from skillflow.experiment.t17.cluster_metrics import (
    T17ClusterBootstrapRequest,
    build_cluster_bootstrap_intervals,
    cluster_consistency,
)
from skillflow.experiment.t17.contracts import (
    EvidenceDomain,
    EvidenceDomainKind,
    HookName,
    MeasurementStatus,
    RatioMeasurement,
)
from skillflow.experiment.t17.live_attempt_models import (
    T17LivePreflightManifest,
    T17LiveStageSummary,
    T17LiveUnitKind,
    T17LiveUnitRecord,
)
from skillflow.experiment.t17.live_matrix import T17LiveMatrix, load_live_matrix
from skillflow.experiment.t17.metric_models import (
    T17CausalImpactSummary,
    T17PhaseMetricsReport,
    T17ProvenanceReport,
    T17UeaSummary,
)
from skillflow.experiment.t17.metric_statistics import (
    ScheduledRatioContext,
    scheduled_ratio,
    wilson_interval,
)
from skillflow.experiment.t17.phase_advanced import advanced_metric_statuses
from skillflow.experiment.t17.phase_efficiency import (
    build_efficiency_summary,
    phase_source_hashes,
)
from skillflow.experiment.t17.phase_integrity import (
    T17PhaseIntegrityRequest,
    validate_phase_integrity,
)
from skillflow.experiment.t17.phase_report_loader import (
    T17LoadedPhaseArtifacts,
    load_phase_artifacts,
)
from skillflow.experiment.t17.scenario_registry import (
    T17ConditionKind,
    T17ScenarioMeasurementRegistry,
    load_scenario_measurement_registry,
)
from skillflow.experiment.t17.scripted_provenance import (
    aggregate_scripted_provenance,
)
from skillflow.models.matrix import ExperimentMatrix
from skillflow.validation import validate_yaml_document


@dataclass(frozen=True, slots=True)
class T17PhaseReportRequest:
    """Phase 报告的 Attempt、Matrix、Registry 与输出路径。"""

    attempt_root: Path
    matrix_path: Path
    registry_path: Path
    base_matrix_path: Path
    output_path: Path


def build_phase_metrics_report(
    request: T17PhaseReportRequest,
) -> T17PhaseMetricsReport:
    """复验 Raw SHA 后计算 scheduled 主口径和 observed-only 旧聚合。"""
    matrix = load_live_matrix(request.matrix_path)
    registry = load_scenario_measurement_registry(request.registry_path)
    base_matrix = validate_yaml_document(request.base_matrix_path, ExperimentMatrix)
    stored_summary = T17LiveStageSummary.model_validate_json(
        (request.attempt_root / "live-summary.json").read_text(encoding="utf-8")
    )
    preflight = T17LivePreflightManifest.model_validate_json(
        (request.attempt_root / "preflight.json").read_text(encoding="utf-8")
    )
    loaded = load_phase_artifacts(request.attempt_root)
    stage_summary = validate_phase_integrity(
        T17PhaseIntegrityRequest(
            request.attempt_root,
            matrix,
            registry,
            preflight,
            loaded,
            stored_summary,
        )
    )
    fallback = base_matrix.hiaa_designs[0].harm_selector
    standard = aggregate_standard_results(
        StandardAggregationInput(
            experiment_id=request.attempt_root.parent.parent.name,
            runs=loaded.runs,
            replays=loaded.replays,
            fallback_selector=fallback,
        )
    )
    core_records = tuple(item for item in loaded.records if item.unit_kind is T17LiveUnitKind.CORE)
    replay_records = tuple(
        item for item in loaded.records if item.unit_kind is T17LiveUnitKind.REPLAY
    )
    ratios = _task_and_effect_ratios(matrix, registry, loaded, core_records)
    uea = _uea_summary(matrix, loaded, core_records)
    causal = _causal_summary(matrix, loaded, replay_records)
    consistency = cluster_consistency(
        matrix,
        loaded.records,
        loaded.runs_by_trial,
    )
    provenance = _provenance_report(matrix, loaded)
    all_ratios = {**ratios, "uea_affected_trial": uea.affected_trial_rate}
    all_ratios["replay_nonzero_ci"] = causal.nonzero_rate
    all_ratios["cluster_consistency"] = consistency
    complete = stage_summary.live_gate_passed
    advanced_statuses = advanced_metric_statuses(standard)
    bootstrap = build_cluster_bootstrap_intervals(
        T17ClusterBootstrapRequest(
            matrix,
            registry,
            loaded.records,
            loaded.runs_by_trial,
            standard,
            complete,
        )
    )
    formal_stage = matrix.stage.value in {"model1", "model2", "defense"}
    required_metrics_complete = (
        complete
        and all(
            measurement.status is MeasurementStatus.MEASURED
            for measurement in (
                *ratios.values(),
                uea.affected_trial_rate,
                causal.nonzero_rate,
            )
        )
        and provenance.status is MeasurementStatus.MEASURED
        and all(status is MeasurementStatus.MEASURED for status in advanced_statuses.values())
        and (
            consistency.status is MeasurementStatus.MEASURED
            if formal_stage
            else consistency.status is MeasurementStatus.NOT_APPLICABLE
        )
        and all(
            interval.status
            is (MeasurementStatus.MEASURED if formal_stage else MeasurementStatus.NOT_APPLICABLE)
            for interval in bootstrap.values()
        )
    )
    return T17PhaseMetricsReport(
        report_id=f"{request.attempt_root.parent.parent.name}-{matrix.stage.value}-metrics-v1",
        required_metrics_complete=required_metrics_complete,
        evidence_domain=EvidenceDomain(
            domain_id=(
                f"t17-{matrix.stage.value}-{matrix.provider.model_revision}-reference-harness-v1"
            ),
            kind=EvidenceDomainKind.REFERENCE_HARNESS,
            simulation_only=False,
            external_effects_simulated=True,
            protocol_id="t17-live-reference-v1",
            provider="openai",
            model_id=matrix.provider.model_id,
            model_revision=matrix.provider.model_revision,
        ),
        stage_summary=stage_summary,
        standard_risk_report=standard,
        standard_risk_scope=("scheduled_complete" if complete else "observed_only_sensitivity"),
        task_success_rate=ratios["task_success"],
        safe_task_success_rate=ratios["safe_task_success"],
        benign_refusal_rate=ratios["benign_refusal"],
        verified_target_effect_rate=ratios["verified_target_effect"],
        uea=uea,
        provenance=provenance,
        causal_impact=causal,
        cluster_consistency=consistency,
        advanced_metric_statuses=advanced_statuses,
        wilson_intervals={
            name: wilson_interval(measurement) for name, measurement in all_ratios.items()
        },
        bootstrap_intervals=bootstrap,
        efficiency=build_efficiency_summary(loaded.records, stage_summary),
        source_artifact_sha256=phase_source_hashes(
            request.attempt_root,
            request.matrix_path,
            request.registry_path,
        ),
    )


def write_phase_metrics_report(request: T17PhaseReportRequest) -> T17PhaseMetricsReport:
    """构造并不可覆盖写出 Phase 指标。"""
    report = build_phase_metrics_report(request)
    request.output_path.parent.mkdir(parents=True, exist_ok=True)
    write_json_model(request.output_path, report)
    return report


def _task_and_effect_ratios(
    matrix: T17LiveMatrix,
    registry: T17ScenarioMeasurementRegistry,
    loaded: T17LoadedPhaseArtifacts,
    core_records: tuple[T17LiveUnitRecord, ...],
) -> dict[str, RatioMeasurement]:
    specifications = {item.scenario_id: item for item in registry.scenarios}
    benign_trials = {
        trial.trial_id
        for trial in matrix.trials
        if specifications[trial.scenario_id].condition_kind is T17ConditionKind.BENIGN_CONTROL
    }
    observed_benign = tuple(item for item in core_records if item.trial_id in benign_trials)
    vte_records = tuple(
        item
        for item in core_records
        if item.trial_id in loaded.runs_by_trial
        and loaded.runs_by_trial[item.trial_id].harm_effect_ids
    )
    return {
        "task_success": scheduled_ratio(
            sum(item.task_success is True for item in core_records),
            len(core_records),
            matrix.scheduled_core_trials,
            ScheduledRatioContext(
                evidence_ids=tuple(
                    item.unit_id for item in core_records if item.task_success is True
                )
            ),
        ),
        "safe_task_success": scheduled_ratio(
            sum(item.safe_task_success is True for item in core_records),
            len(core_records),
            matrix.scheduled_core_trials,
            ScheduledRatioContext(
                evidence_ids=tuple(
                    item.unit_id for item in core_records if item.safe_task_success is True
                )
            ),
        ),
        "benign_refusal": scheduled_ratio(
            sum(item.telemetry.refusal_count > 0 for item in observed_benign),
            len(observed_benign),
            len(benign_trials),
            ScheduledRatioContext(
                evidence_ids=tuple(
                    item.unit_id for item in observed_benign if item.telemetry.refusal_count > 0
                )
            ),
        ),
        "verified_target_effect": scheduled_ratio(
            len(vte_records),
            len(core_records),
            matrix.scheduled_core_trials,
            ScheduledRatioContext(
                evidence_ids=tuple(
                    effect_id
                    for item in vte_records
                    for effect_id in loaded.runs_by_trial[item.trial_id].harm_effect_ids
                )
            ),
        ),
    }


def _uea_summary(
    matrix: T17LiveMatrix,
    loaded: T17LoadedPhaseArtifacts,
    core_records: tuple[T17LiveUnitRecord, ...],
) -> T17UeaSummary:
    authorization_records = []
    for item in core_records:
        snapshot = loaded.observations_by_trial.get(item.trial_id)
        if snapshot is None:
            continue
        capability = next(value for value in snapshot.hooks if value.hook is HookName.AUTHORIZATION)
        if capability.status is MeasurementStatus.MEASURED:
            authorization_records.append(item)
    affected = tuple(
        item
        for item in authorization_records
        if loaded.runs_by_trial[item.trial_id].uea.uea_count > 0
    )
    effect_ids = tuple(
        effect.effect_id for run in loaded.runs for effect in run.unauthorized_effects
    )
    keys = tuple(
        dict.fromkeys(
            json.dumps(
                key.model_dump(mode="json"),
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            for run in loaded.runs
            for key in run.uea.canonical_effect_keys
        )
    )
    return T17UeaSummary(
        uea_count=sum(run.uea.uea_count for run in loaded.runs),
        uea_type_count=len(keys),
        uea_weight=sum(run.uea.uea_weight for run in loaded.runs),
        affected_trial_rate=scheduled_ratio(
            len(affected),
            len(authorization_records),
            matrix.scheduled_core_trials,
            ScheduledRatioContext(
                evidence_ids=tuple(effect_ids),
                incomplete_reason=("Authorization Hook 尚未覆盖全部 scheduled Trial"),
            ),
        ),
        effect_ids=effect_ids,
        canonical_effect_keys=keys,
    )


def _causal_summary(
    matrix: T17LiveMatrix,
    loaded: T17LoadedPhaseArtifacts,
    replay_records: tuple[T17LiveUnitRecord, ...],
) -> T17CausalImpactSummary:
    negative = tuple(item for item in loaded.replays if item.ci == -1)
    zero = tuple(item for item in loaded.replays if item.ci == 0)
    positive = tuple(item for item in loaded.replays if item.ci == 1)
    confirmed = tuple(
        evidence_id
        for item in loaded.replays
        for edge in item.confirmed_influence_edges
        for evidence_id in (edge.source_artifact_id, edge.target_effect_id)
    )
    return T17CausalImpactSummary(
        negative_count=len(negative),
        zero_count=len(zero),
        positive_count=len(positive),
        nonzero_rate=scheduled_ratio(
            len(negative) + len(positive),
            len(replay_records),
            matrix.scheduled_replay_pairs,
            ScheduledRatioContext(
                evidence_ids=tuple(item.replay_id for item in (*negative, *positive))
            ),
        ),
        replay_ids=tuple(item.replay_id for item in loaded.replays),
        confirmed_influence_evidence_ids=confirmed,
    )


def _provenance_report(
    matrix: T17LiveMatrix,
    loaded: T17LoadedPhaseArtifacts,
) -> T17ProvenanceReport:
    metrics = None if not loaded.runs else aggregate_scripted_provenance(loaded.runs)
    if len(loaded.runs) < matrix.scheduled_core_trials:
        return T17ProvenanceReport(
            status=MeasurementStatus.INCOMPLETE,
            observed_runs=len(loaded.runs),
            scheduled_runs=matrix.scheduled_core_trials,
            metrics=metrics,
            reason="阶段未完成全部 provenance Run",
        )
    available = all(
        next(
            item
            for item in loaded.observations_by_trial[trial_id].hooks
            if item.hook is HookName.PROVENANCE
        ).status
        is MeasurementStatus.MEASURED
        for trial_id in loaded.runs_by_trial
    )
    return T17ProvenanceReport(
        status=(MeasurementStatus.MEASURED if available else MeasurementStatus.NOT_AVAILABLE),
        observed_runs=len(loaded.runs),
        scheduled_runs=matrix.scheduled_core_trials,
        metrics=metrics,
        reason=None if available else "required provenance Hook 缺少受信证据",
    )
