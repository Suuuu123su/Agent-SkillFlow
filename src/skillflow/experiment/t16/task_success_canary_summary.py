"""从 Canary 原始记录和逐响应用量机械构造阶段摘要。"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal, cast

from skillflow.experiment.t16.budget import BudgetLedger
from skillflow.experiment.t16.live_canary_usage_models import CanaryUsageJournalEvent
from skillflow.experiment.t16.live_record_builders import add_usage
from skillflow.experiment.t16.live_usage_store import ActualUsageStatus, LiveTrialTerminalStatus
from skillflow.experiment.t16.provider import TokenUsage
from skillflow.experiment.t16.task_success_canary_models import (
    T16D2CanaryRunSummary,
    T16D2CanaryTrialSummary,
)
from skillflow.experiment.t16.task_success_canary_preflight import T16D2CanaryInputs
from skillflow.experiment.t16.task_success_live_integrity import sha256_file
from skillflow.experiment.t16.task_success_live_models import (
    T16D2PreflightManifest,
    T16D2RawTrialRecord,
    T16D2StageGate,
    T16D2StopReason,
)


@dataclass(frozen=True, slots=True)
class CanarySummaryInputs:
    """摘要构造所需的冻结文件、终态与状态。"""

    prepared: T16D2CanaryInputs
    records: tuple[T16D2RawTrialRecord, ...]
    usage_events: tuple[CanaryUsageJournalEvent, ...]
    budget: BudgetLedger
    created_at: datetime
    manifest: T16D2PreflightManifest
    config_id: str
    config_sha256: str
    raw_path: Path
    usage_path: Path
    gate: T16D2StageGate
    stop_reason: T16D2StopReason | None
    stop_detail: str | None


def build_canary_run_summary(inputs: CanarySummaryInputs) -> T16D2CanaryRunSummary:
    """只聚合每条 Trial 的终态事件，避免重复累计响应快照。"""
    terminals = tuple(item for item in inputs.usage_events if item.event_type == "terminal")
    terminal_by_trial = {item.trial_id: item for item in terminals}
    raw_by_trial = {item.live_trial.result.trial_id: item for item in inputs.records}
    trials = tuple(
        _trial_summary(terminal_by_trial[f"live--{item.trial_id}"], raw_by_trial)
        for item in inputs.prepared.schedule
        if f"live--{item.trial_id}" in terminal_by_trial
    )
    usage_status = _aggregate_usage_status(terminals)
    observed_usage = _aggregate_tokens(terminals)
    observed_cost = _aggregate_cost(terminals)
    evaluations = tuple(
        item.live_trial.task_success_result
        for item in inputs.records
        if item.live_trial.task_success_result is not None
    )
    executed = sum(item.live_trial.result.target_effect_executed for item in inputs.records)
    receipts = sum(item.live_trial.result.receipt_id is not None for item in inputs.records)
    revisions = {revision for item in inputs.records for revision in item.provider_model_revisions}
    revisions.update(item.model_revision for item in terminals if item.model_revision is not None)
    m2_target = next((item for item in trials if item.condition_id == "m2-target"), None)
    status: Literal["PASSED", "BLOCKED"] = (
        "PASSED" if inputs.gate.passed and inputs.stop_reason is None else "BLOCKED"
    )
    return T16D2CanaryRunSummary(
        created_at=inputs.created_at,
        status=status,
        protocol_id="t16-task-success-bridge-preregistration-v3.1",
        config_id=inputs.config_id,
        config_sha256=inputs.config_sha256,
        phase_contract_sha256=inputs.manifest.phase_contract_sha256,
        observed=len(inputs.records),
        unrun=11 - len(inputs.records),
        canary_gate_passed=inputs.gate.passed,
        stop_reason=inputs.stop_reason,
        stop_detail=inputs.stop_detail,
        infrastructure_invalid=sum(_infrastructure_invalid(item) for item in inputs.records),
        pairs_complete=inputs.prepared.pairs_complete,
        c1_harm_selector_shared=inputs.prepared.c1_harm_selector_shared,
        task_success_result_count=len(evaluations),
        task_success_evidence_count=sum(
            len(item.live_trial.task_success_evidence) for item in inputs.records
        ),
        passed_assertion_count=sum(len(item.passed_assertion_ids) for item in evaluations),
        failed_assertion_count=sum(len(item.failed_assertion_ids) for item in evaluations),
        not_evaluable_assertion_count=sum(
            len(item.not_evaluable_assertion_ids) for item in evaluations
        ),
        task_success_true=sum(
            item.live_trial.result.task_success is True for item in inputs.records
        ),
        task_success_false=sum(
            item.live_trial.result.task_success is False for item in inputs.records
        ),
        task_success_na=sum(item.live_trial.result.task_success is None for item in inputs.records),
        target_effect_requested_count=sum(
            item.live_trial.result.target_effect_requested for item in inputs.records
        ),
        target_effect_executed_count=executed,
        target_effect_receipt_count=receipts,
        receipt_coverage_complete=executed == receipts,
        actual_usage_status=usage_status,
        observed_token_usage=observed_usage,
        observed_estimated_cost_usd=observed_cost,
        conservative_reserved_usd=inputs.budget.total_spent_usd,
        api_call_count=sum(item.api_call_count for item in terminals),
        m2_target_actual_steps=(m2_target.agent_steps if m2_target is not None else None),
        provider_model_revisions=tuple(sorted(revisions)),
        raw_records_sha256=sha256_file(inputs.raw_path),
        usage_journal_sha256=sha256_file(inputs.usage_path),
        trials=trials,
    )


def _trial_summary(
    terminal: CanaryUsageJournalEvent,
    records: dict[str, T16D2RawTrialRecord],
) -> T16D2CanaryTrialSummary:
    record = records.get(terminal.trial_id)
    result = record.live_trial.result if record is not None else None
    return T16D2CanaryTrialSummary(
        trial_id=terminal.trial_id,
        condition_id=terminal.condition_id,
        agent_steps=terminal.api_call_count,
        completed_session_indices=terminal.completed_session_indices,
        terminal_status=cast("LiveTrialTerminalStatus", terminal.terminal_status),
        actual_usage_status=terminal.actual_usage_status,
        observed_token_usage=terminal.observed_token_usage,
        observed_estimated_cost_usd=terminal.observed_estimated_cost_usd,
        task_success=(result.task_success if result is not None else None),
        target_effect_requested=(result.target_effect_requested if result is not None else None),
        target_effect_executed=(result.target_effect_executed if result is not None else None),
        receipt_id=(result.receipt_id if result is not None else None),
        refusal=(result.refusal if result is not None else None),
        no_call=(result.no_call if result is not None else None),
        schema_rejection=(result.schema_rejection if result is not None else None),
        provider_model_revision=terminal.model_revision,
    )


def _aggregate_usage_status(
    terminals: tuple[CanaryUsageJournalEvent, ...],
) -> ActualUsageStatus:
    calls = sum(item.api_call_count for item in terminals)
    responses = sum(item.response_count for item in terminals)
    if responses == 0:
        return ActualUsageStatus.NOT_AVAILABLE
    if responses < calls:
        return ActualUsageStatus.PARTIAL
    return ActualUsageStatus.COMPLETE


def _aggregate_tokens(terminals: tuple[CanaryUsageJournalEvent, ...]) -> TokenUsage | None:
    observed = tuple(
        item.observed_token_usage for item in terminals if item.observed_token_usage is not None
    )
    if not observed:
        return None
    total = observed[0]
    for usage in observed[1:]:
        total = add_usage(total, usage)
    return total


def _aggregate_cost(terminals: tuple[CanaryUsageJournalEvent, ...]) -> Decimal | None:
    observed = tuple(
        item.observed_estimated_cost_usd
        for item in terminals
        if item.observed_estimated_cost_usd is not None
    )
    return sum(observed, start=Decimal(0)) if observed else None


def _infrastructure_invalid(record: T16D2RawTrialRecord) -> bool:
    result = record.live_trial.result
    return result.timeout or result.rate_limit or result.provider_error
