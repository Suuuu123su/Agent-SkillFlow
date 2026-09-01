"""v3.1 两个模型共用的独立 11 条 Canary 执行引擎。"""

from datetime import UTC, datetime

from pydantic import ValidationError

from skillflow.experiment.t16.budget import BudgetExceededError, BudgetLedger
from skillflow.experiment.t16.live_agent_calls import LiveAgentClient
from skillflow.experiment.t16.live_canary_usage import (
    LiveCanaryMetadataDriftError,
    LiveCanaryUsageJournal,
    LiveTrialTerminalStatus,
    load_canary_usage_events,
)
from skillflow.experiment.t16.live_run_models import LiveGatewayCrashError
from skillflow.experiment.t16.live_store import LiveBudgetJournal
from skillflow.experiment.t16.task_success_canary_engine_support import (
    CANARY_COUNT,
    CanaryRunContract,
    T16D2CanaryRunError,
    T16D2CanaryRunRequest,
    emit_canary_progress,
    require_new_output,
    terminal_status,
)
from skillflow.experiment.t16.task_success_canary_models import T16D2CanaryRunSummary
from skillflow.experiment.t16.task_success_canary_preflight import load_t16d2r_canary_inputs
from skillflow.experiment.t16.task_success_canary_summary import (
    CanarySummaryInputs,
    build_canary_run_summary,
)
from skillflow.experiment.t16.task_success_live_agent import (
    TaskSuccessLiveExecutionOptions,
    execute_task_success_live_trial,
)
from skillflow.experiment.t16.task_success_live_design import build_task_success_live_design
from skillflow.experiment.t16.task_success_live_integrity import (
    build_t16d2r_preflight_manifest,
)
from skillflow.experiment.t16.task_success_live_models import (
    T16D2RawTrialRecord,
    T16D2StopReason,
)
from skillflow.experiment.t16.task_success_live_run_support import (
    T16D2ProgressSink,
    check_immediate_stop,
)
from skillflow.experiment.t16.task_success_live_stage import (
    T16D2StageGateInputs,
    evaluate_stage_gate,
)
from skillflow.experiment.t16.task_success_live_store import (
    T16D2RawStore,
    write_immutable_json,
)


def execute_canary_run(  # noqa: C901, PLR0915
    request: T16D2CanaryRunRequest,
    contract: CanaryRunContract,
    client: LiveAgentClient,
    progress: T16D2ProgressSink | None = None,
) -> T16D2CanaryRunSummary:
    """执行新 Attempt 的 11 条冻结 Canary，不进入剩余 Matrix。"""
    require_new_output(request.output_root)
    prepared = load_t16d2r_canary_inputs(request.project_root)
    config = contract.config
    environment = request.environment
    if (
        environment.provider != contract.provider_name
        or environment.model_id != config.provider.model_id
    ):
        detail = "环境授权与冻结 Canary 配置不一致"
        raise T16D2CanaryRunError(detail)
    if environment.max_total_usd != config.budget.max_total_usd:
        detail = "环境授权预算与冻结 Canary 配置不一致"
        raise T16D2CanaryRunError(detail)
    started_at = datetime.now(UTC)
    manifest = build_t16d2r_preflight_manifest(prepared.inputs, config, started_at)
    output = request.output_root
    write_immutable_json(output / "preflight.json", manifest)
    write_immutable_json(output / "effective-config.json", config)
    raw_path = output / "raw-trials.jsonl"
    raw_store = T16D2RawStore(raw_path)
    raw_store.open_new()
    budget_journal = LiveBudgetJournal(output / "budget-journal.jsonl", config.budget)
    budget_journal.open(resume=False)
    usage_path = output / "actual-usage-journal.jsonl"
    usage_journal = LiveCanaryUsageJournal(usage_path, config, contract.protocol_id)
    usage_journal.open_new()
    by_spec = {item.spec_id: item for item in prepared.inputs.registry.conditions}
    budget = BudgetLedger(config.budget)
    stop_reason: T16D2StopReason | None = None
    stop_detail: str | None = None
    attempt_id = f"{output.parent.name}-{output.name}"
    for trial in prepared.schedule:
        design = build_task_success_live_design(prepared.inputs, trial)
        tracker = usage_journal.start_trial(f"live--{trial.trial_id}", trial.condition_id)
        terminal = LiveTrialTerminalStatus.PARTIAL
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
                    budget_checkpoint=budget_journal,
                    usage_checkpoint=tracker,
                ),
            )
            raw_store.append(
                T16D2RawTrialRecord(
                    task_success_spec_id=execution.task_success_spec_id,
                    provider_model_revisions=execution.provider_model_revisions,
                    platform_evidence_snapshot=execution.snapshot,
                    live_trial=execution.record,
                )
            )
            budget = execution.budget
            trial_saved = True
            terminal, terminal_detail = terminal_status(execution.record.result)
        except BudgetExceededError as error:
            budget = budget_journal.latest_budget()
            stop_reason = T16D2StopReason.BUDGET_LIMIT
            stop_detail = error.limit.value
            terminal = (
                LiveTrialTerminalStatus.STEP_LIMIT_EXHAUSTED
                if error.limit.value == "agent_turns"
                else LiveTrialTerminalStatus.PARTIAL
            )
            terminal_detail = error.limit.value
        except LiveCanaryMetadataDriftError as error:
            budget = budget_journal.latest_budget()
            stop_reason = T16D2StopReason.MODEL_REVISION_CHANGED
            stop_detail = str(error)
            terminal_detail = "provider_or_model_metadata_changed"
        except LiveGatewayCrashError:
            budget = budget_journal.latest_budget()
            stop_reason = T16D2StopReason.GATEWAY_CRASH
            stop_detail = "gateway_crash"
            terminal_detail = "gateway_crash"
        except ValidationError:
            budget = budget_journal.latest_budget()
            stop_reason = T16D2StopReason.EVIDENCE_BINDING
            stop_detail = "platform_binding_validation_failed"
            terminal_detail = "platform_binding_validation_failed"
        finally:
            tracker.finalize(terminal, terminal_detail)
        if not trial_saved:
            break
        records = raw_store.read()
        events = load_canary_usage_events(usage_path)
        terminals = tuple(item for item in events if item.event_type == "terminal")
        emit_canary_progress(progress, records, terminals, budget.total_spent_usd)
        immediate_stop = check_immediate_stop(
            records,
            raw_path,
            config.provider.model_revision,
        )
        if immediate_stop is not None:
            stop_reason, stop_detail = immediate_stop
            break
        if budget.total_spent_usd >= config.budget.max_total_usd and len(records) < CANARY_COUNT:
            stop_reason = T16D2StopReason.BUDGET_LIMIT
            stop_detail = "total_cost"
            break
    records = raw_store.read()
    gate = evaluate_stage_gate(
        T16D2StageGateInputs(
            "canary",
            records,
            prepared.inputs.registry,
            CANARY_COUNT,
            raw_path,
            config.provider.model_revision,
        )
    )
    write_immutable_json(output / "stage-gate-canary.json", gate)
    if not gate.passed and stop_reason is None:
        stop_reason = T16D2StopReason.CANARY_GATE_BLOCKED
        stop_detail = gate.reasons[0]
    events = load_canary_usage_events(usage_path)
    summary = build_canary_run_summary(
        CanarySummaryInputs(
            prepared=prepared,
            records=records,
            usage_events=events,
            budget=budget,
            created_at=started_at,
            manifest=manifest,
            config_id=config.id,
            config_sha256=usage_journal.config_sha256,
            raw_path=raw_path,
            usage_path=usage_path,
            gate=gate,
            stop_reason=stop_reason,
            stop_detail=stop_detail,
        )
    )
    write_immutable_json(output / "run-summary.json", summary)
    return summary
