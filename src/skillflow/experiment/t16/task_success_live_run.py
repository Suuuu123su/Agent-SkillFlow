"""T16-D.2 的 11 条 Canary 与剩余 37 条顺序执行器。"""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from skillflow.experiment.t16.budget import BudgetExceededError, BudgetLedger
from skillflow.experiment.t16.live_agent_calls import LiveAgentClient
from skillflow.experiment.t16.live_run_models import LiveGatewayCrashError
from skillflow.experiment.t16.live_store import LiveBudgetJournal
from skillflow.experiment.t16.live_usage_store import (
    LiveTrialTerminalStatus,
    LiveTrialUsageTracker,
    LiveUsageJournal,
)
from skillflow.experiment.t16.task_success_live_agent import (
    TaskSuccessLiveExecutionOptions,
    execute_task_success_live_trial,
)
from skillflow.experiment.t16.task_success_live_config import (
    T16D2R_PROTOCOL_ID,
    build_t16d2_live_config,
    build_t16d2r_live_config,
)
from skillflow.experiment.t16.task_success_live_design import (
    build_task_success_live_design,
)
from skillflow.experiment.t16.task_success_live_integrity import (
    build_t16d2_preflight_manifest,
    build_t16d2r_preflight_manifest,
)
from skillflow.experiment.t16.task_success_live_models import (
    T16D2RawTrialRecord,
    T16D2RunSummary,
    T16D2StopReason,
)
from skillflow.experiment.t16.task_success_live_preflight import (
    T16D2Environment,
    load_t16d2_inputs,
    load_t16d2r_inputs,
    select_canary_trials,
)
from skillflow.experiment.t16.task_success_live_report import build_t16d2_bridge_report
from skillflow.experiment.t16.task_success_live_run_support import (
    CANARY_COUNT,
    CHECKPOINT_COUNTS,
    TRIAL_COUNT,
    T16D2ProgressEvent,
    T16D2ProgressSink,
    build_run_summary,
    check_immediate_stop,
    emit_progress,
    predicted_total_usd,
    write_checkpoint,
)
from skillflow.experiment.t16.task_success_live_stage import evaluate_t16d2_stage_gate
from skillflow.experiment.t16.task_success_live_store import (
    T16D2RawStore,
    load_t16d2_raw_records,
    write_immutable_json,
)

ENVIRONMENT_BUDGET_MISMATCH = "环境授权预算与冻结 Live 配置不一致"


@dataclass(frozen=True, slots=True)
class T16D2RunRequest:
    """一次全新 D.2 Attempt 的项目、输出与非秘密授权。"""

    project_root: Path
    output_root: Path
    environment: T16D2Environment


def execute_t16d2_run(
    request: T16D2RunRequest,
    client: LiveAgentClient,
    progress: T16D2ProgressSink | None = None,
) -> T16D2RunSummary:
    """执行冻结的原 v3 协议；保留旧入口以防止历史语义漂移。"""
    return _execute_t16d2_run(request, client, progress, revised=False)


def execute_t16d2r_run(
    request: T16D2RunRequest,
    client: LiveAgentClient,
    progress: T16D2ProgressSink | None = None,
) -> T16D2RunSummary:
    """执行不可与 v3 合并的 v3.1 新 Attempt，并保存逐响应用量。"""
    return _execute_t16d2_run(request, client, progress, revised=True)


def _execute_t16d2_run(  # noqa: C901, PLR0912, PLR0915
    request: T16D2RunRequest,
    client: LiveAgentClient,
    progress: T16D2ProgressSink | None,
    *,
    revised: bool,
) -> T16D2RunSummary:
    """先执行 Canary，通过技术门后才运行剩余 Trial。"""
    inputs = (
        load_t16d2r_inputs(request.project_root)
        if revised
        else load_t16d2_inputs(request.project_root)
    )
    config = (
        build_t16d2r_live_config(request.project_root)
        if revised
        else build_t16d2_live_config(request.project_root)
    )
    if config.budget.max_total_usd != request.environment.max_total_usd:
        raise ValueError(ENVIRONMENT_BUDGET_MISMATCH)
    started_at = datetime.now(UTC)
    manifest = (
        build_t16d2r_preflight_manifest(inputs, config, started_at)
        if revised
        else build_t16d2_preflight_manifest(inputs, started_at)
    )
    output = request.output_root
    write_immutable_json(output / "preflight.json", manifest)
    raw_path = output / "raw-trials.jsonl"
    store = T16D2RawStore(raw_path)
    store.open_new()
    journal = LiveBudgetJournal(output / "budget-journal.jsonl", config.budget)
    journal.open(resume=False)
    usage_journal: LiveUsageJournal | None = None
    if revised:
        usage_journal = LiveUsageJournal(
            output / "actual-usage-journal.jsonl",
            config,
            protocol_id=T16D2R_PROTOCOL_ID,
        )
        usage_journal.open_new()
    by_spec = {item.spec_id: item for item in inputs.registry.conditions}
    canary = select_canary_trials(inputs.matrix)
    canary_ids = {item.trial_id for item in canary}
    remaining = tuple(item for item in inputs.matrix.trials if item.trial_id not in canary_ids)
    schedule = (*canary, *remaining)
    budget = BudgetLedger(config.budget)
    stop_reason: T16D2StopReason | None = None
    stop_detail: str | None = None
    canary_gate_passed = False
    final_gate_passed = False
    attempt_id = f"{output.parent.name}-{output.name}"
    for trial in schedule:
        records = store.read()
        prediction = predicted_total_usd(records, budget, len(schedule) - len(records))
        if prediction > config.budget.max_total_usd:
            stop_reason = T16D2StopReason.P95_BUDGET_PREDICTION
            stop_detail = "p95_projected_total_above_3_usd"
            break
        design = build_task_success_live_design(inputs, trial)
        usage_tracker: LiveTrialUsageTracker | None = None
        if usage_journal is not None:
            usage_tracker = usage_journal.start_trial(f"live--{trial.trial_id}")
        terminal_status = LiveTrialTerminalStatus.PARTIAL
        terminal_detail: str | None = "partial"
        trial_saved = False
        try:
            execution = execute_task_success_live_trial(
                design,
                by_spec[trial.task_success_spec_id],
                config,
                client,
                budget.begin_run(),
                TaskSuccessLiveExecutionOptions(
                    run_id=f"{attempt_id}--{trial.trial_id}",
                    created_at=datetime.now(UTC),
                    phase_contract_sha256=manifest.phase_contract_sha256,
                    budget_checkpoint=journal,
                    usage_checkpoint=usage_tracker,
                ),
            )
            raw = T16D2RawTrialRecord(
                task_success_spec_id=execution.task_success_spec_id,
                provider_model_revisions=execution.provider_model_revisions,
                platform_evidence_snapshot=execution.snapshot,
                live_trial=execution.record,
            )
            store.append(raw)
            budget = execution.budget
            trial_saved = True
            terminal_status, terminal_detail = _terminal_status(execution.record.result)
        except BudgetExceededError as error:
            budget = journal.latest_budget()
            stop_reason = T16D2StopReason.BUDGET_LIMIT
            stop_detail = error.limit.value
            terminal_status = (
                LiveTrialTerminalStatus.STEP_LIMIT_EXHAUSTED
                if error.limit.value == "agent_turns"
                else LiveTrialTerminalStatus.PARTIAL
            )
            terminal_detail = error.limit.value
        except LiveGatewayCrashError:
            budget = journal.latest_budget()
            stop_reason = T16D2StopReason.GATEWAY_CRASH
            stop_detail = "gateway_crash"
            terminal_detail = "gateway_crash"
        except ValidationError:
            budget = journal.latest_budget()
            stop_reason = T16D2StopReason.EVIDENCE_BINDING
            stop_detail = "platform_binding_validation_failed"
            terminal_detail = "platform_binding_validation_failed"
        finally:
            if usage_tracker is not None:
                usage_tracker.finalize(terminal_status, terminal_detail)
        if not trial_saved:
            break
        records = store.read()
        if len(records) in CHECKPOINT_COUNTS:
            write_checkpoint(output, records, budget, started_at, raw_path)
        emit_progress(progress, records, budget)
        immediate_stop = check_immediate_stop(records, raw_path)
        if immediate_stop is not None:
            stop_reason, stop_detail = immediate_stop
            break
        if len(records) == CANARY_COUNT:
            canary_gate = evaluate_t16d2_stage_gate(
                "canary",
                records,
                inputs.registry,
                CANARY_COUNT,
                raw_path,
            )
            write_immutable_json(output / "stage-gate-canary.json", canary_gate)
            canary_gate_passed = canary_gate.passed
            if not canary_gate.passed:
                stop_reason = T16D2StopReason.CANARY_GATE_BLOCKED
                stop_detail = canary_gate.reasons[0]
                break
    records = store.read()
    if len(records) == TRIAL_COUNT and stop_reason is None:
        final_gate = evaluate_t16d2_stage_gate(
            "final",
            records,
            inputs.registry,
            TRIAL_COUNT,
            raw_path,
        )
        write_immutable_json(output / "stage-gate-final.json", final_gate)
        final_gate_passed = final_gate.passed
        if not final_gate.passed:
            stop_reason = T16D2StopReason.EVIDENCE_BINDING
            stop_detail = final_gate.reasons[0]
    summary = build_run_summary(
        records,
        budget,
        started_at,
        raw_path,
        canary_gate_passed,
        final_gate_passed,
        stop_reason,
        stop_detail,
    )
    write_immutable_json(output / "run-summary.json", summary)
    write_immutable_json(
        output / "bridge-report.json",
        build_t16d2_bridge_report(records, summary),
    )
    return summary


__all__ = (
    "T16D2ProgressEvent",
    "T16D2ProgressSink",
    "T16D2RunRequest",
    "T16D2StopReason",
    "execute_t16d2_run",
    "execute_t16d2r_run",
    "load_t16d2_raw_records",
)


def _terminal_status(result: object) -> tuple[LiveTrialTerminalStatus, str | None]:
    """把已落盘 Trial 的 Provider 基础设施终态标成 partial。"""
    provider_error = bool(getattr(result, "provider_error", False))
    timeout = bool(getattr(result, "timeout", False))
    rate_limit = bool(getattr(result, "rate_limit", False))
    if provider_error:
        return LiveTrialTerminalStatus.PARTIAL, "provider_error"
    if timeout:
        return LiveTrialTerminalStatus.PARTIAL, "timeout"
    if rate_limit:
        return LiveTrialTerminalStatus.PARTIAL, "rate_limit"
    return LiveTrialTerminalStatus.COMPLETED, None
