"""T16-C Smoke/Model1 的可恢复顺序执行器。

顺序执行状态机与可审计汇总保持共置，避免恢复语义跨模块漂移。# noqa: SIZE_OK
"""

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Protocol

from skillflow.experiment.t16.budget import BudgetExceededError, BudgetLedger
from skillflow.experiment.t16.live_agent import LiveTrialExecutionOptions, execute_live_trial
from skillflow.experiment.t16.live_agent_calls import LiveAgentClient
from skillflow.experiment.t16.live_config import T16CLiveConfig, load_t16c_config
from skillflow.experiment.t16.live_design import build_live_trial_design
from skillflow.experiment.t16.live_design_models import LiveTrialDesign
from skillflow.experiment.t16.live_phase_contract import (
    LivePhaseContractInputs,
    build_phase_contract_sha256,
)
from skillflow.experiment.t16.live_record_builders import add_usage, zero_usage
from skillflow.experiment.t16.live_records import LiveTrialRecord
from skillflow.experiment.t16.live_run_models import (
    LiveFailureCounts,
    LiveGatewayCrashError,
    LivePhase,
    LivePhaseSummary,
    LiveResultCounts,
    LiveStopReason,
)
from skillflow.experiment.t16.live_store import (
    LiveBudgetJournal,
    LivePhaseContractStore,
    LiveResultStore,
)
from skillflow.experiment.t16.matrix import (
    T16Matrix,
    TrialSpec,
    load_matrix,
    validate_matrix_against_preregistration,
)
from skillflow.experiment.t16.preregistration import (
    load_preregistration,
    verify_scenario_bindings,
)
from skillflow.experiment.t16.preregistration_models import T16Preregistration
from skillflow.experiment.t16.trial import ProvenanceStatus, TrialOutcome
from skillflow.models.scenario import Scenario

HTTP_CLIENT_ERROR_MIN = 400
HTTP_SERVER_ERROR_MIN = 500


@dataclass(frozen=True, slots=True)
class LivePhaseRequest:
    """一次固定阶段执行所需的路径、恢复和前序保守占用。"""

    project_root: Path
    output_root: Path
    phase: LivePhase
    resume: bool = False
    initial_total_reserved_usd: Decimal = Decimal(0)


@dataclass(frozen=True, slots=True)
class LiveResumeContractError(RuntimeError):
    """已有 Trial 不能证明属于当前付费执行合同。"""

    trial_id: str
    detail: str

    def __str__(self) -> str:
        """只返回字段级诊断，不泄露模型输入。"""
        return f"resume contract [{self.trial_id}]: {self.detail}"


@dataclass(frozen=True, slots=True)
class _SummaryContext:
    request: LivePhaseRequest
    config: T16CLiveConfig
    matrix_id: str
    expected: int
    resumed_count: int


@dataclass(frozen=True, slots=True)
class _StopState:
    reason: LiveStopReason | None = None
    detail: str | None = None


@dataclass(slots=True)
class _ModelRevisionGuard:
    """记住阶段内首个实际 revision，并检测后续响应切换。"""

    model_revision: str | None = None

    def changed(self, record: LiveTrialRecord) -> bool:
        """基础设施失败没有实际 revision，不参与切换判断。"""
        actual_revision = _actual_model_revision(record)
        if actual_revision is None:
            return False
        if self.model_revision is None:
            self.model_revision = actual_revision
            return False
        return actual_revision != self.model_revision


@dataclass(frozen=True, slots=True)
class _ResumeValidationContext:
    registration: T16Preregistration
    matrix: T16Matrix
    config: T16CLiveConfig
    scenarios: dict[str, Scenario]
    phase_contract_sha256: str


@dataclass(frozen=True, slots=True)
class LiveProgressEvent:
    """不含 Prompt、响应或凭据的单 Trial 进度。"""

    phase: LivePhase
    completed: int
    expected: int
    conservative_reserved_usd: Decimal


class LiveProgressSink(Protocol):
    """CLI 可注入的安全进度输出边界。"""

    def __call__(self, event: LiveProgressEvent) -> None:
        """接收一次不含敏感内容的进度事件。"""
        ...


def execute_live_phase(
    request: LivePhaseRequest,
    client: LiveAgentClient,
    progress: LiveProgressSink | None = None,
) -> LivePhaseSummary:
    """逐条保存真实模型结果；预算或 Gateway 边界失败时立即停止。"""
    registration, matrix, config, scenarios = load_live_phase_inputs(request)
    phase_contract_sha256 = build_phase_contract_sha256(
        LivePhaseContractInputs(
            request.project_root,
            request.phase,
            config,
            registration,
            matrix,
            scenarios,
        )
    )
    contract_store = LivePhaseContractStore(request.output_root / "phase-contract.json")
    result_store = LiveResultStore(request.output_root / "trial-results.jsonl")
    journal = LiveBudgetJournal(request.output_root / "budget-journal.jsonl", config.budget)
    contract_store.open(
        resume=request.resume,
        phase=request.phase.value,
        phase_contract_sha256=phase_contract_sha256,
    )
    result_store.open(resume=request.resume)
    existing_records = result_store.read_records()
    if request.resume:
        _validate_resume_records(
            existing_records,
            _ResumeValidationContext(
                registration,
                matrix,
                config,
                scenarios,
                phase_contract_sha256,
            ),
        )
    journal.open(resume=request.resume)
    resumed_count = len(result_store.completed_trial_ids)
    budget = _initial_budget(request, config, journal)
    existing_failure = _first_infrastructure_failure(
        existing_records,
        request.phase,
    )
    stop_reason = LiveStopReason.INFRASTRUCTURE_FAILURE if existing_failure is not None else None
    stop_detail = existing_failure
    revision_guard = _ModelRevisionGuard(
        next(
            (
                revision
                for record in existing_records
                if (revision := _actual_model_revision(record)) is not None
            ),
            None,
        ),
    )
    for spec in matrix.trials:
        if stop_reason is not None:
            break
        if f"live--{spec.trial_id}" in result_store.completed_trial_ids:
            continue
        try:
            execution = execute_live_trial(
                build_live_trial_design(registration, spec, scenarios[spec.condition_id]),
                config,
                client,
                budget.begin_run(),
                LiveTrialExecutionOptions(
                    budget_checkpoint=journal,
                    phase_contract_sha256=phase_contract_sha256,
                ),
            )
        except BudgetExceededError as error:
            stop_reason = LiveStopReason.BUDGET_LIMIT
            stop_detail = error.limit.value
            break
        except LiveGatewayCrashError:
            stop_reason = LiveStopReason.GATEWAY_CRASH
            stop_detail = LiveStopReason.GATEWAY_CRASH.value
            break
        result_store.append(execution.record)
        budget = execution.budget
        if progress is not None:
            progress(
                LiveProgressEvent(
                    request.phase,
                    len(result_store.completed_trial_ids),
                    len(matrix.trials),
                    budget.total_spent_usd,
                )
            )
        post_record_stop = _post_record_stop(
            execution.record,
            request.phase,
            revision_guard,
        )
        if post_record_stop.reason is not None:
            stop_reason = post_record_stop.reason
            stop_detail = post_record_stop.detail
            break
    records = result_store.read_records()
    summary = _build_summary(
        _SummaryContext(
            request,
            config,
            matrix.id,
            len(matrix.trials),
            resumed_count,
        ),
        records,
        journal,
        _StopState(stop_reason, stop_detail),
    )
    _write_summary(request.output_root / "phase-summary.json", summary)
    return summary


def load_live_phase_inputs(
    request: LivePhaseRequest,
) -> tuple[T16Preregistration, T16Matrix, T16CLiveConfig, dict[str, Scenario]]:
    """加载并闭合复核 T16-C v2 的预注册、矩阵、配置与 Scenario。"""
    t16_root = request.project_root / "experiments" / "t16"
    registration = load_preregistration(t16_root / "preregistration_t16c_v2.yaml")
    scenarios = verify_scenario_bindings(registration, request.project_root)
    matrix_name = (
        "matrix_smoke_t16c_v2.yaml"
        if request.phase is LivePhase.SMOKE
        else "matrix_model1_t16c_v2.yaml"
    )
    matrix = load_matrix(t16_root / matrix_name)
    validate_matrix_against_preregistration(matrix, registration)
    config = load_t16c_config(t16_root / "t16c_live.yaml")
    if request.phase is LivePhase.SMOKE:
        smoke_budget = config.budget.model_copy(
            update={"max_total_usd": config.smoke_max_total_usd}
        )
        config = config.model_copy(update={"budget": smoke_budget})
    return registration, matrix, T16CLiveConfig.model_validate(config.model_dump()), scenarios


def _validate_resume_records(
    records: tuple[LiveTrialRecord, ...],
    context: _ResumeValidationContext,
) -> None:
    """在任何新 Client 调用前重编译并复核全部已有 Trial。"""
    specs = {item.trial_id: item for item in context.matrix.trials}
    revisions: set[str] = set()
    for record in records:
        trial_id = record.matrix_trial_id
        if record.schema_version != "0.2":
            raise LiveResumeContractError(trial_id, "schema_version 必须为 0.2")
        if record.phase_contract_sha256 != context.phase_contract_sha256:
            raise LiveResumeContractError(trial_id, "phase_contract_sha256 不一致")
        spec = specs.get(trial_id)
        if spec is None:
            raise LiveResumeContractError(trial_id, "Trial 不属于 current Matrix")
        _require_trial_identity(record, spec)
        design = build_live_trial_design(
            context.registration,
            spec,
            context.scenarios[spec.condition_id],
        )
        _require_design_identity(record, design)
        _require_provider_identity(record, context.config)
        actual_revision = _actual_model_revision(record)
        if actual_revision is not None:
            revisions.add(actual_revision)
    if len(revisions) > 1:
        raise LiveResumeContractError("phase", "已有 records 的 model_revision 不唯一")


def _require_trial_identity(record: LiveTrialRecord, spec: TrialSpec) -> None:
    result = record.result
    expected = (
        ("result.trial_id", result.trial_id, f"live--{spec.trial_id}"),
        ("scenario", result.scenario, spec.scenario),
        ("condition_id", result.condition_id, spec.condition_id),
        ("semantic_instance_id", result.semantic_instance_id, spec.semantic_instance_id),
        ("pair_id", result.pair_id, spec.pair_id),
        ("repeat_index", result.repeat_index, spec.repeat_index),
    )
    for field, actual, wanted in expected:
        if actual != wanted:
            raise LiveResumeContractError(record.matrix_trial_id, f"{field} 与 TrialSpec 不一致")


def _require_design_identity(record: LiveTrialRecord, design: LiveTrialDesign) -> None:
    model_input_sha256 = hashlib.sha256(design.serialized_model_input().encode()).hexdigest()
    expected = (
        ("pair_role", record.pair_role, design.pair_role),
        ("independent_factor", record.independent_factor, design.independent_factor),
        ("hiaa_cell", record.hiaa_cell, design.hiaa_cell),
        ("harm_selector", record.harm_selector, design.harm_selector),
        (
            "authorization_request_id",
            record.authorization_request_id,
            design.authorization_request_id,
        ),
        (
            "structured_target_authorized",
            record.structured_target_authorized,
            design.structured_target_authorized,
        ),
        (
            "decision_basis_artifact_ids",
            record.decision_basis_artifact_ids,
            design.decision_basis_artifact_ids,
        ),
        (
            "baseline_reason",
            record.baseline_reason,
            design.baseline_reason if record.result.target_effect_executed else None,
        ),
        ("intervention", record.intervention, design.intervention),
        ("model_input_sha256", record.model_input_sha256, model_input_sha256),
        (
            "expected_target_effect_aliases",
            record.expected_target_effect_aliases,
            design.target_effect_aliases,
        ),
    )
    for field, actual, wanted in expected:
        if actual != wanted:
            raise LiveResumeContractError(record.matrix_trial_id, f"{field} 与当前设计不一致")
    expected_sessions = design.sessions[: len(record.sessions)]
    actual_indices = tuple(item.session_index for item in record.sessions)
    expected_indices = tuple(item.session_index for item in expected_sessions)
    if actual_indices != expected_indices:
        raise LiveResumeContractError(record.matrix_trial_id, "Session 序列与当前设计不一致")
    for session_record, session_design in zip(record.sessions, expected_sessions, strict=True):
        if (
            session_record.expected_target_effect_aliases
            != session_design.expected_target_effect_aliases
        ):
            raise LiveResumeContractError(
                record.matrix_trial_id,
                f"session-{session_record.session_index} target aliases 与当前设计不一致",
            )


def _require_provider_identity(record: LiveTrialRecord, config: T16CLiveConfig) -> None:
    result = record.result
    expected = (
        ("provider", result.provider, config.provider.kind),
        ("model_id", result.model_id, config.provider.model_id),
        ("temperature", result.temperature, config.provider.temperature),
        ("reasoning_effort", result.reasoning_effort, config.provider.reasoning_effort),
        ("max_agent_turns", result.max_agent_turns, config.budget.max_agent_turns),
    )
    for field, actual, wanted in expected:
        if actual != wanted:
            raise LiveResumeContractError(
                record.matrix_trial_id,
                f"{field} 与当前 Provider/config 不一致",
            )


def _actual_model_revision(record: LiveTrialRecord) -> str | None:
    """仅返回 Provider 真正产生响应时报告的 revision，排除失败回退 alias。"""
    result = record.result
    if result.timeout or result.rate_limit or result.provider_error:
        return None
    return result.model_revision


def _post_record_stop(
    record: LiveTrialRecord,
    phase: LivePhase,
    revision_guard: _ModelRevisionGuard,
) -> _StopState:
    if revision_guard.changed(record):
        return _StopState(LiveStopReason.CONTRACT_MISMATCH, "model_revision_changed")
    infrastructure_failure = _record_infrastructure_failure(record, phase)
    if infrastructure_failure is not None:
        return _StopState(LiveStopReason.INFRASTRUCTURE_FAILURE, infrastructure_failure)
    return _StopState()


def _initial_budget(
    request: LivePhaseRequest,
    config: T16CLiveConfig,
    journal: LiveBudgetJournal,
) -> BudgetLedger:
    if request.resume:
        return journal.latest_budget()
    budget = BudgetLedger(
        config.budget,
        total_spent_usd=request.initial_total_reserved_usd,
    )
    if request.initial_total_reserved_usd:
        journal.record(budget)
    return budget


def _build_summary(
    context: _SummaryContext,
    records: tuple[LiveTrialRecord, ...],
    journal: LiveBudgetJournal,
    stop: _StopState,
) -> LivePhaseSummary:
    usage = zero_usage()
    for record in records:
        usage = add_usage(usage, record.result.token_usage)
    failures = _failure_counts(records, stop.reason)
    complete = len(records) == context.expected and stop.reason is None
    return LivePhaseSummary(
        phase=context.request.phase,
        model_id=context.config.provider.model_id,
        model_revision_config=context.config.provider.model_revision,
        matrix_id=context.matrix_id,
        expected_trial_count=context.expected,
        completed_trial_count=len(records),
        unique_trial_id_count=len({item.result.trial_id for item in records}),
        resumed_trial_count=context.resumed_count,
        new_trial_count=len(records) - context.resumed_count,
        stopped=stop.reason is not None,
        stop_reason=stop.reason,
        stop_detail=stop.detail,
        live_gate_passed=(complete and failures.gate_blocking_total(context.request.phase) == 0),
        result_counts=_result_counts(records),
        failure_counts=failures,
        token_usage=usage,
        api_call_count=sum(item.result.api_call_count for item in records),
        actual_estimated_cost_usd=sum(
            (item.result.estimated_cost_usd for item in records),
            start=Decimal(0),
        ),
        conservative_reserved_usd=journal.latest_budget().total_spent_usd,
        trial_results_sha256=_sha256(context.request.output_root / "trial-results.jsonl"),
        budget_journal_sha256=_sha256(context.request.output_root / "budget-journal.jsonl"),
        provenance_not_available_count=sum(
            item.result.provenance.status is ProvenanceStatus.NOT_AVAILABLE for item in records
        ),
    )


def _result_counts(records: tuple[LiveTrialRecord, ...]) -> LiveResultCounts:
    return LiveResultCounts(
        harm=sum(item.result.outcome is TrialOutcome.HARM for item in records),
        completed_without_harm=sum(
            item.result.outcome is TrialOutcome.COMPLETED_WITHOUT_HARM for item in records
        ),
        invalid=sum(item.result.outcome is TrialOutcome.INVALID for item in records),
    )


def _failure_counts(
    records: tuple[LiveTrialRecord, ...],
    stop_reason: LiveStopReason | None,
) -> LiveFailureCounts:
    return LiveFailureCounts(
        refusal=sum(item.result.refusal for item in records),
        no_call=sum(item.result.no_call for item in records),
        schema_rejection=sum(item.result.schema_rejection for item in records),
        timeout=sum(item.result.timeout for item in records),
        rate_limit=sum(item.result.rate_limit for item in records),
        provider_error=sum(item.result.provider_error for item in records),
        gateway_crash=int(stop_reason is LiveStopReason.GATEWAY_CRASH),
    )


def _record_infrastructure_failure(
    record: LiveTrialRecord,
    phase: LivePhase,
) -> str | None:
    result = record.result
    provider_detail, provider_status = _provider_failure(record)
    if phase is LivePhase.SMOKE:
        checks = (
            (result.schema_rejection, "schema_rejection"),
            (result.timeout, "timeout"),
            (result.rate_limit, "rate_limit"),
            (result.provider_error, provider_detail),
            (result.gateway_crash, "gateway_crash"),
        )
        return next((name for failed, name in checks if failed), None)
    nonretryable_provider = (
        result.provider_error
        and provider_status is not None
        and HTTP_CLIENT_ERROR_MIN <= provider_status < HTTP_SERVER_ERROR_MIN
    )
    model1_checks = (
        (nonretryable_provider, provider_detail),
        (result.gateway_crash, "gateway_crash"),
    )
    return next((name for failed, name in model1_checks if failed), None)


def _provider_failure(record: LiveTrialRecord) -> tuple[str, int | None]:
    session = next(
        (session for session in record.sessions if session.provider_error),
        None,
    )
    if session is None:
        return "provider_error", None
    details = ["provider_error"]
    if session.provider_status_code is not None:
        details.append(f"status={session.provider_status_code}")
    if session.provider_error_type is not None:
        details.append(f"type={session.provider_error_type}")
    if session.provider_error_code is not None:
        details.append(f"code={session.provider_error_code}")
    if session.provider_error_param is not None:
        details.append(f"param={session.provider_error_param}")
    return ":".join(details), session.provider_status_code


def _first_infrastructure_failure(
    records: tuple[LiveTrialRecord, ...],
    phase: LivePhase,
) -> str | None:
    for record in records:
        failure = _record_infrastructure_failure(record, phase)
        if failure is not None:
            return failure
    return None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_summary(path: Path, summary: LivePhaseSummary) -> None:
    content = json.dumps(summary.model_dump(mode="json"), ensure_ascii=False, indent=2)
    path.write_text(f"{content}\n", encoding="utf-8")
