"""T17 Live 阶段完整性、Hook、Receipt 和实际用量汇总。"""

from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from skillflow.experiment.io import sha256_file
from skillflow.experiment.t16.live_record_builders import add_usage, zero_usage
from skillflow.experiment.t17.contracts import (
    HookCapability,
    HookName,
    MeasurementStatus,
    RatioMeasurement,
)
from skillflow.experiment.t17.live_attempt_models import (
    T17LiveFailureKind,
    T17LiveStageSummary,
    T17LiveTerminalStatus,
    T17LiveUnitKind,
    T17LiveUnitRecord,
)
from skillflow.experiment.t17.live_matrix import T17LiveMatrix
from skillflow.experiment.t17.live_reference_client import ReferenceLiveTelemetry
from skillflow.experiment.t17.observation_models import ReferenceObservationSnapshot
from skillflow.experiment.t17.scenario_registry import T17ScenarioMeasurementRegistry


@dataclass(frozen=True, slots=True)
class T17LiveSummaryRequest:
    """构造单阶段摘要所需的 Raw 与静态调度输入。"""

    attempt_root: Path
    matrix: T17LiveMatrix
    registry: T17ScenarioMeasurementRegistry
    records: tuple[T17LiveUnitRecord, ...]
    stop_detail: str | None


def build_live_stage_summary(
    request: T17LiveSummaryRequest,
) -> T17LiveStageSummary:
    """从 Raw 索引和逐 Run 观察机械计算阶段门。"""
    attempt_root = request.attempt_root
    matrix = request.matrix
    registry = request.registry
    records = request.records
    core_records = tuple(item for item in records if item.unit_kind is T17LiveUnitKind.CORE)
    replay_records = tuple(item for item in records if item.unit_kind is T17LiveUnitKind.REPLAY)
    completed_core = tuple(
        item for item in core_records if item.terminal_status is T17LiveTerminalStatus.COMPLETED
    )
    completed_replay = tuple(
        item for item in replay_records if item.terminal_status is T17LiveTerminalStatus.COMPLETED
    )
    snapshots = {item.trial_id: _load_snapshot(attempt_root, item) for item in completed_core}
    completion = _coverage(
        len(completed_core) + len(completed_replay),
        len(records),
        matrix.scheduled_core_trials + matrix.scheduled_replay_pairs,
        tuple(item.unit_id for item in records),
        "阶段尚未产生全部调度单元终态",
    )
    task_coverage = _coverage(
        sum(snapshot.task_success is not None for snapshot in snapshots.values()),
        len(core_records),
        matrix.scheduled_core_trials,
        tuple(
            value
            for snapshot in snapshots.values()
            if snapshot.task_success is not None
            for value in snapshot.task_success.evidence_ids
        ),
        "阶段尚未关闭全部 TaskSuccessEvidence 分母",
    )
    receipt_complete = sum(_receipt_complete(snapshot) for snapshot in snapshots.values())
    receipt_coverage = _coverage(
        receipt_complete,
        len(core_records),
        matrix.scheduled_core_trials,
        tuple(
            effect.receipt_id
            for snapshot in snapshots.values()
            for effect in snapshot.effects
            if effect.receipt_id is not None
        ),
        "阶段尚未关闭全部核心 Trial 的 Receipt 分母",
    )
    usage_coverage = _coverage(
        sum(item.telemetry.api_call_count == item.telemetry.response_count for item in records),
        len(records),
        matrix.scheduled_core_trials + matrix.scheduled_replay_pairs,
        tuple(item.unit_id for item in records),
        "阶段尚未关闭全部调度单元的实际用量分母",
    )
    influence_coverage = _coverage(
        len(completed_replay),
        len(replay_records),
        matrix.scheduled_replay_pairs,
        tuple(value for item in completed_replay for value in item.evidence_ids),
        "阶段尚未关闭全部 Replay Influence 分母",
    )
    hooks, hook_coverage = _aggregate_hooks(matrix, registry, snapshots, replay_records)
    telemetry = _aggregate_telemetry(records)
    failures = Counter(item.failure_kind for item in records if item.failure_kind is not None)
    gate = (
        all(
            _is_complete(measurement)
            for measurement in (
                completion,
                task_coverage,
                receipt_coverage,
                usage_coverage,
                influence_coverage,
                hook_coverage,
            )
        )
        and not failures
    )
    return T17LiveStageSummary(
        stage=matrix.stage,
        model_id=matrix.provider.model_id,
        model_revision=matrix.provider.model_revision,
        scheduled_core_trials=matrix.scheduled_core_trials,
        scheduled_replay_pairs=matrix.scheduled_replay_pairs,
        completed_core_trials=len(completed_core),
        completed_replay_pairs=len(completed_replay),
        completion=completion,
        task_success_evidence_coverage=task_coverage,
        receipt_coverage=receipt_coverage,
        actual_usage_coverage=usage_coverage,
        replay_influence_coverage=influence_coverage,
        required_hook_coverage=hook_coverage,
        hooks=hooks,
        telemetry=telemetry,
        schema_failure_count=failures[T17LiveFailureKind.SCHEMA],
        provider_4xx_count=failures[T17LiveFailureKind.PROVIDER_4XX],
        infrastructure_failure_count=failures[T17LiveFailureKind.INFRASTRUCTURE],
        evidence_binding_failure_count=failures[T17LiveFailureKind.EVIDENCE_BINDING],
        budget_stop_count=failures[T17LiveFailureKind.BUDGET],
        revision_drift_count=failures[T17LiveFailureKind.MODEL_REVISION],
        refusal_count=telemetry.refusal_count,
        no_call_count=telemetry.no_call_count,
        live_gate_passed=gate,
        stop_detail=request.stop_detail,
        preflight_sha256=sha256_file(attempt_root / "preflight.json"),
        usage_journal_sha256=sha256_file(attempt_root / "actual-usage-journal.jsonl"),
        trial_results_sha256=sha256_file(attempt_root / "trial-results.jsonl"),
    )


def _load_snapshot(
    attempt_root: Path,
    record: T17LiveUnitRecord,
) -> ReferenceObservationSnapshot:
    path = next(
        (
            attempt_root / item.relative_path
            for item in record.artifacts
            if item.relative_path.endswith("/t17-observations.json")
        ),
        None,
    )
    if path is None:
        detail = f"{record.unit_id}:observation_digest_missing"
        raise ValueError(detail)
    return ReferenceObservationSnapshot.model_validate_json(path.read_text(encoding="utf-8"))


def _receipt_complete(snapshot: ReferenceObservationSnapshot) -> bool:
    return all(not item.executed or item.receipt_id is not None for item in snapshot.effects)


def _aggregate_hooks(
    matrix: T17LiveMatrix,
    registry: T17ScenarioMeasurementRegistry,
    snapshots: dict[str, ReferenceObservationSnapshot],
    replay_records: tuple[T17LiveUnitRecord, ...],
) -> tuple[tuple[HookCapability, ...], RatioMeasurement]:
    specifications = {item.scenario_id: item for item in registry.scenarios}
    expected: Counter[HookName] = Counter()
    observed: Counter[HookName] = Counter()
    measured: Counter[HookName] = Counter()
    evidence: dict[HookName, list[str]] = defaultdict(list)
    for trial in matrix.trials:
        specification = specifications[trial.scenario_id]
        snapshot = snapshots.get(trial.trial_id)
        by_hook = {} if snapshot is None else {item.hook: item for item in snapshot.hooks}
        for hook in specification.required_hooks:
            if hook is HookName.INFLUENCE:
                continue
            expected[hook] += 1
            capability = by_hook.get(hook)
            if capability is None:
                continue
            observed[hook] += 1
            if capability.status is MeasurementStatus.MEASURED:
                measured[hook] += 1
                evidence[hook].extend(capability.evidence_ids)
    expected[HookName.INFLUENCE] = matrix.scheduled_replay_pairs
    observed[HookName.INFLUENCE] = len(replay_records)
    completed_replay = tuple(
        item for item in replay_records if item.terminal_status is T17LiveTerminalStatus.COMPLETED
    )
    measured[HookName.INFLUENCE] = len(completed_replay)
    evidence[HookName.INFLUENCE].extend(
        value for item in completed_replay for value in item.evidence_ids
    )
    capabilities = tuple(
        _stage_hook(
            hook,
            expected[hook],
            observed[hook],
            measured[hook],
            tuple(dict.fromkeys(evidence[hook])),
        )
        for hook in HookName
    )
    expected_total = sum(expected.values())
    observed_total = sum(observed.values())
    measured_total = sum(measured.values())
    return capabilities, _coverage(
        measured_total,
        observed_total,
        expected_total,
        tuple(value for item in capabilities for value in item.evidence_ids),
        "阶段尚未关闭全部 required Hook 分母",
    )


def _stage_hook(
    hook: HookName,
    expected: int,
    observed: int,
    measured: int,
    evidence_ids: tuple[str, ...],
) -> HookCapability:
    if expected == 0:
        return HookCapability(
            hook=hook,
            required=False,
            available=False,
            status=MeasurementStatus.NOT_APPLICABLE,
            reason="该阶段设计不要求此 Hook",
        )
    if observed < expected and measured > 0:
        return HookCapability(
            hook=hook,
            required=True,
            available=True,
            status=MeasurementStatus.INCOMPLETE,
            reason="该阶段仅完成部分 required Hook 观察",
            evidence_ids=evidence_ids,
        )
    if observed == expected and measured == expected:
        return HookCapability(
            hook=hook,
            required=True,
            available=True,
            status=MeasurementStatus.MEASURED,
            evidence_ids=evidence_ids,
        )
    return HookCapability(
        hook=hook,
        required=True,
        available=False,
        status=MeasurementStatus.NOT_AVAILABLE,
        reason="required Hook 存在未绑定受信证据的观察",
        evidence_ids=evidence_ids,
    )


def _coverage(
    numerator: int,
    observed: int,
    scheduled: int,
    evidence_ids: tuple[str, ...],
    incomplete_reason: str,
) -> RatioMeasurement:
    if scheduled == 0:
        return RatioMeasurement(
            status=MeasurementStatus.NOT_APPLICABLE,
            reason="该阶段没有此类调度单元",
        )
    if observed < scheduled:
        return RatioMeasurement(
            status=MeasurementStatus.INCOMPLETE,
            numerator=numerator,
            denominator=observed,
            scheduled_denominator=scheduled,
            reason=incomplete_reason,
            evidence_ids=evidence_ids,
        )
    return RatioMeasurement(
        status=MeasurementStatus.MEASURED,
        numerator=numerator,
        denominator=scheduled,
        scheduled_denominator=scheduled,
        value=numerator / scheduled,
        evidence_ids=evidence_ids,
    )


def _aggregate_telemetry(
    records: tuple[T17LiveUnitRecord, ...],
) -> ReferenceLiveTelemetry:
    usage = zero_usage()
    for item in records:
        usage = add_usage(usage, item.telemetry.token_usage)
    return ReferenceLiveTelemetry(
        api_call_count=sum(item.telemetry.api_call_count for item in records),
        response_count=sum(item.telemetry.response_count for item in records),
        agent_step_count=sum(item.telemetry.agent_step_count for item in records),
        retry_count=sum(item.telemetry.retry_count for item in records),
        refusal_count=sum(item.telemetry.refusal_count for item in records),
        no_call_count=sum(item.telemetry.no_call_count for item in records),
        token_usage=usage,
        latency_ms=sum(item.telemetry.latency_ms for item in records),
        estimated_cost_usd=sum(
            (item.telemetry.estimated_cost_usd for item in records),
            start=Decimal(0),
        ),
        conservative_reserved_usd=sum(
            (item.telemetry.conservative_reserved_usd for item in records),
            start=Decimal(0),
        ),
    )


def _is_complete(measurement: RatioMeasurement) -> bool:
    return measurement.status is MeasurementStatus.MEASURED and measurement.value == 1.0
