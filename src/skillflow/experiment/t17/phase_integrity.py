"""T17 Phase 门对 Journal、Raw、Observation 与 Summary 的交叉复验。"""

from dataclasses import dataclass
from pathlib import Path

from skillflow.experiment.t16.live_record_builders import zero_usage
from skillflow.experiment.t17.live_attempt_models import (
    T17LivePreflightManifest,
    T17LiveStageSummary,
    T17LiveTerminalStatus,
    T17LiveUnitKind,
    T17LiveUnitRecord,
)
from skillflow.experiment.t17.live_journal import load_live_journal
from skillflow.experiment.t17.live_journal_models import T17LiveJournalEvent
from skillflow.experiment.t17.live_matrix import (
    T17LiveMatrix,
    T17LiveStage,
    T17LiveTrial,
)
from skillflow.experiment.t17.live_summary import (
    T17LiveSummaryRequest,
    build_live_stage_summary,
)
from skillflow.experiment.t17.observations import build_influence_observations
from skillflow.experiment.t17.phase_report_loader import (
    T17LoadedPhaseArtifacts,
)
from skillflow.experiment.t17.scenario_registry import (
    T17ScenarioMeasurement,
    T17ScenarioMeasurementRegistry,
)


class T17PhaseIntegrityError(RuntimeError):
    """Phase Raw 之间存在不可接受的不一致。"""

    __slots__ = ("detail", "identifier")

    def __init__(self, identifier: str, detail: str) -> None:
        """保存安全身份和封闭 reason code。"""
        super().__init__(identifier, detail)
        self.identifier = identifier
        self.detail = detail

    def __str__(self) -> str:
        """返回不含正文和宿主路径的稳定诊断。"""
        return f"{self.identifier}:{self.detail}"


@dataclass(frozen=True, slots=True)
class T17PhaseIntegrityRequest:
    """Phase Raw 交叉复验的完整输入。"""

    attempt_root: Path
    matrix: T17LiveMatrix
    registry: T17ScenarioMeasurementRegistry
    preflight: T17LivePreflightManifest
    loaded: T17LoadedPhaseArtifacts
    stored_summary: T17LiveStageSummary


def validate_phase_integrity(
    request: T17PhaseIntegrityRequest,
) -> T17LiveStageSummary:
    """验证日志链、终态、强任务证据和机械重建 Summary。"""
    attempt_root = request.attempt_root
    matrix = request.matrix
    registry = request.registry
    preflight = request.preflight
    loaded = request.loaded
    events = load_live_journal(attempt_root / "actual-usage-journal.jsonl")
    terminals = tuple(item for item in events if item.event_type == "terminal")
    if tuple(item.unit_id for item in terminals) != tuple(item.unit_id for item in loaded.records):
        raise T17PhaseIntegrityError("journal", "terminal_identity_mismatch")
    specifications = {item.scenario_id: item for item in registry.scenarios}
    trials = {item.trial_id: item for item in matrix.trials}
    for record, event in zip(loaded.records, terminals, strict=True):
        _require_schedule_match(record, trials, matrix.stage)
        _require_terminal_match(record, event)
        if record.unit_kind is T17LiveUnitKind.CORE:
            _require_core_match(record, loaded, specifications)
        else:
            _require_replay_match(record, loaded)
    stop_detail = _stop_detail(loaded.records)
    rebuilt = build_live_stage_summary(
        T17LiveSummaryRequest(
            attempt_root,
            matrix,
            registry,
            loaded.records,
            stop_detail,
        )
    )
    if rebuilt != request.stored_summary:
        raise T17PhaseIntegrityError("live-summary", "mechanical_rebuild_mismatch")
    if any(
        item.phase_contract_sha256 != preflight.phase_contract_sha256
        or item.approved_config_sha256 != preflight.approved_config_sha256
        for item in events
    ):
        raise T17PhaseIntegrityError("journal", "preflight_binding_mismatch")
    return rebuilt


def _require_terminal_match(
    record: T17LiveUnitRecord,
    event: T17LiveJournalEvent,
) -> None:
    telemetry = record.telemetry
    observed_usage = event.observed_token_usage or zero_usage()
    observed_cost = event.observed_estimated_cost_usd or 0
    values_match = (
        event.trial_id == record.trial_id
        and event.unit_kind is record.unit_kind
        and event.stage is record.stage
        and event.terminal_status is record.terminal_status
        and event.failure_kind is record.failure_kind
        and event.failure_detail == record.failure_detail
        and event.failure_diagnostic == record.failure_diagnostic
        and event.api_call_count == telemetry.api_call_count
        and event.response_count == telemetry.response_count
        and event.agent_step_count == telemetry.agent_step_count
        and event.retry_count == telemetry.retry_count
        and event.refusal_count == telemetry.refusal_count
        and event.no_call_count == telemetry.no_call_count
        and event.latency_ms == telemetry.latency_ms
        and observed_usage == telemetry.token_usage
        and observed_cost == telemetry.estimated_cost_usd
        and event.run_reserved_usd == telemetry.conservative_reserved_usd
    )
    if not values_match:
        raise T17PhaseIntegrityError(record.unit_id, "journal_record_mismatch")


def _require_schedule_match(
    record: T17LiveUnitRecord,
    trials: dict[str, T17LiveTrial],
    stage: T17LiveStage,
) -> None:
    trial = trials.get(record.trial_id)
    if trial is None:
        raise T17PhaseIntegrityError(record.unit_id, "trial_not_scheduled")
    if (
        record.stage is not stage
        or record.variant != trial.variant
        or record.source_variant != trial.source_variant
        or record.enforcement_mode is not trial.enforcement_mode
        or record.scenario_id != trial.scenario_id
        or record.semantic_instance_id != trial.semantic_instance_id
        or record.semantic_template_id != trial.semantic_template_id
        or record.repeat_index != trial.repeat_index
    ):
        raise T17PhaseIntegrityError(record.unit_id, "schedule_identity_mismatch")


def _require_core_match(
    record: T17LiveUnitRecord,
    loaded: T17LoadedPhaseArtifacts,
    specifications: dict[str, T17ScenarioMeasurement],
) -> None:
    snapshot = loaded.observations_by_trial[record.trial_id]
    run = loaded.runs_by_trial[record.trial_id]
    task = snapshot.task_success
    if task is None:
        raise T17PhaseIntegrityError(record.unit_id, "task_evidence_missing")
    risk_executed = _risk_effect_executed(
        run.effects,
        specifications[record.scenario_id],
    )
    safe_task_success = task.task_success and not risk_executed
    expected_evidence = tuple(
        dict.fromkeys(
            (
                *task.evidence_ids,
                *(item.receipt_id for item in snapshot.effects if item.receipt_id is not None),
                *(value for hook in snapshot.hooks for value in hook.evidence_ids),
            )
        )
    )
    if (
        record.run_ids != (run.run_id,)
        or record.task_success is not task.task_success
        or run.task_success is not task.task_success
        or record.safe_task_success is not safe_task_success
        or record.evidence_ids != expected_evidence
    ):
        raise T17PhaseIntegrityError(record.unit_id, "core_evidence_mismatch")


def _require_replay_match(
    record: T17LiveUnitRecord,
    loaded: T17LoadedPhaseArtifacts,
) -> None:
    report = loaded.replays_by_unit[record.unit_id]
    expected_evidence = build_influence_observations((report,))[0].evidence_ids
    if record.replay_ids != (report.replay_id,) or record.evidence_ids != expected_evidence:
        raise T17PhaseIntegrityError(record.unit_id, "replay_identity_mismatch")


def _risk_effect_executed(
    effects: tuple[object, ...],
    specification: T17ScenarioMeasurement,
) -> bool:
    aliases = {item.alias for item in specification.risk_effect_aliases}
    return any(
        getattr(item, "executed", False)
        and (
            getattr(item, "effect_alias", None) in aliases
            or bool(aliases.intersection(getattr(item, "selector_aliases", ())))
        )
        for item in effects
    )


def _stop_detail(
    records: tuple[T17LiveUnitRecord, ...],
) -> str | None:
    if not records:
        return None
    final = records[-1]
    if final.terminal_status is T17LiveTerminalStatus.COMPLETED:
        return None
    if final.failure_kind is None or final.failure_detail is None:
        raise T17PhaseIntegrityError(final.unit_id, "failure_detail_missing")
    return f"{final.failure_kind.value}:{final.failure_detail}"
