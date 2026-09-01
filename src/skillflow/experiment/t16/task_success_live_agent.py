"""T16-D.2 多 Session Live 执行与平台 TaskSuccessEvidence 桥接。"""

from dataclasses import dataclass
from datetime import datetime

from skillflow.experiment.t16.budget import BudgetLedger
from skillflow.experiment.t16.live_agent_calls import (
    ActualUsageCheckpoint,
    BudgetCheckpoint,
    LiveAgentClient,
    SessionAwareUsageCheckpoint,
)
from skillflow.experiment.t16.live_agent_session import SessionRuntimeContext, execute_session
from skillflow.experiment.t16.live_config import T16CLiveConfig
from skillflow.experiment.t16.live_record_builders import (
    LiveRecordEvidence,
    LiveTaskSuccessBinding,
    build_live_trial_record,
)
from skillflow.experiment.t16.live_records import LiveSessionRecord, LiveTrialRecord
from skillflow.experiment.t16.live_tools import LiveToolName, LiveToolRuntime
from skillflow.experiment.t16.task_success_evaluator import (
    TaskSuccessEvaluationContext,
    evaluate_task_success,
)
from skillflow.experiment.t16.task_success_facts import (
    ArtifactRegistrationRequest,
    PlatformEvidenceSnapshot,
    PlatformSessionTrace,
    TaskResultArtifactRegistry,
)
from skillflow.experiment.t16.task_success_live_design import (
    TaskSuccessLiveTrialDesign,
)
from skillflow.experiment.t16.task_success_output import StructuredTaskResultV3
from skillflow.experiment.t16.task_success_spec_models import (
    TaskSuccessConditionSpecification,
)

SPECIFICATION_DESIGN_MISMATCH = "TaskSuccess specification 与 Live design 不一致"


@dataclass(frozen=True, slots=True)
class TaskSuccessLiveExecutionOptions:
    """Trial 私有 Run 身份、确定性时间与持久化合同。"""

    run_id: str
    created_at: datetime
    phase_contract_sha256: str
    budget_checkpoint: BudgetCheckpoint | None = None
    usage_checkpoint: ActualUsageCheckpoint | None = None


@dataclass(frozen=True, slots=True)
class TaskSuccessLiveExecution:
    """可保存的 LiveTrialRecord 与可复算平台事实。"""

    record: LiveTrialRecord
    snapshot: PlatformEvidenceSnapshot
    budget: BudgetLedger
    provider_model_revisions: tuple[str, ...]
    task_success_spec_id: str


def execute_task_success_live_trial(  # noqa: PLR0913, PLR0917
    design: TaskSuccessLiveTrialDesign,
    specification: TaskSuccessConditionSpecification,
    config: T16CLiveConfig,
    client: LiveAgentClient,
    budget: BudgetLedger,
    options: TaskSuccessLiveExecutionOptions,
) -> TaskSuccessLiveExecution:
    """执行一条 v3 Trial；Evidence 只来自本地平台 Hook。"""
    if specification.spec_id != design.task_success_spec_id:
        raise ValueError(SPECIFICATION_DESIGN_MISMATCH)
    runtime = LiveToolRuntime(
        run_nonce=design.matrix_trial_id,
        assets=design.assets,
        effect_alias_catalog={
            binding.public_alias: binding.actual_alias
            for session in design.sessions
            for binding in session.effect_alias_bindings
        },
        platform_run_id=options.run_id,
    )
    context = SessionRuntimeContext(
        config,
        client,
        runtime,
        options.budget_checkpoint,
        options.usage_checkpoint,
    )
    current = budget
    sessions: list[LiveSessionRecord] = []
    retries: list[str] = []
    revisions: list[str] = []
    structured_result = None
    final_session_index = design.sessions[-1].session_index
    for session in design.sessions:
        if isinstance(options.usage_checkpoint, SessionAwareUsageCheckpoint):
            options.usage_checkpoint.activate_session(session.session_index)
        runtime.activate_session(session.session_index)
        runtime.activate_effect_aliases(session.allowed_effect_aliases)
        executed = execute_session(session, context, current)
        current = executed.budget
        record_payload = executed.record.model_dump(mode="python")
        record_payload["expected_target_effect_aliases"] = session.expected_target_effect_aliases
        session_record = LiveSessionRecord.model_validate(record_payload)
        sessions.append(session_record)
        if isinstance(options.usage_checkpoint, SessionAwareUsageCheckpoint):
            options.usage_checkpoint.complete_session(session.session_index)
        retries.extend(executed.retry_events)
        if executed.model_revision is not None:
            revisions.append(executed.model_revision)
        if session.session_index == final_session_index:
            structured_result = executed.structured_task_result
        if _is_infrastructure_failure(session_record):
            break
    snapshot = _platform_snapshot(
        design,
        options.run_id,
        tuple(sessions),
        runtime,
        structured_result,
    )
    trial_id = f"live--{design.matrix_trial_id}"
    evaluation = evaluate_task_success(
        TaskSuccessEvaluationContext(
            run_id=options.run_id,
            trial_id=trial_id,
            created_at=options.created_at,
        ),
        specification.assertions,
        snapshot,
    )
    trial_record = build_live_trial_record(
        design,
        config,
        tuple(sessions),
        LiveRecordEvidence(
            retry_events=tuple(retries),
            model_revision=revisions[0] if revisions else None,
            phase_contract_sha256=options.phase_contract_sha256,
        ),
        task_success_binding=LiveTaskSuccessBinding(options.run_id, evaluation),
    )
    return TaskSuccessLiveExecution(
        record=trial_record,
        snapshot=snapshot,
        budget=current,
        provider_model_revisions=tuple(revisions),
        task_success_spec_id=specification.spec_id,
    )


def _platform_snapshot(
    design: TaskSuccessLiveTrialDesign,
    run_id: str,
    sessions: tuple[LiveSessionRecord, ...],
    runtime: LiveToolRuntime,
    structured_result: StructuredTaskResultV3 | None,
) -> PlatformEvidenceSnapshot:
    registry = TaskResultArtifactRegistry()
    if structured_result is not None:
        final_session = design.sessions[-1].session_index
        producer_step = sum(len(item.tool_calls) for item in sessions) + 1
        registry.register_structured_result(
            ArtifactRegistrationRequest(
                run_id=run_id,
                trial_id=f"live--{design.matrix_trial_id}",
                session_id=f"session-{final_session}",
                producer_step=producer_step,
                platform_alias=design.final_artifact_alias,
            ),
            structured_result,
        )
        if _accepted_tool(sessions, LiveToolName.READ_MEMORY):
            for ordinal, alias in enumerate(design.supplemental_artifact_aliases, start=1):
                registry.register_structured_result(
                    ArtifactRegistrationRequest(
                        run_id=run_id,
                        trial_id=f"live--{design.matrix_trial_id}",
                        session_id=f"session-{final_session}",
                        producer_step=producer_step + ordinal,
                        platform_alias=alias,
                    ),
                    structured_result,
                )
    traces = tuple(
        PlatformSessionTrace(
            session_id=f"session-{item.session_index}",
            reached=True,
            accepted_tool_sequence=tuple(
                call.tool_name for call in item.tool_calls if call.accepted
            ),
        )
        for item in sessions
    )
    return PlatformEvidenceSnapshot(
        artifact_registry_available=True,
        receipt_registry_available=True,
        session_trace_available=True,
        artifacts=registry.artifacts,
        receipts=runtime.platform_receipts,
        sessions=traces,
    )


def _accepted_tool(
    sessions: tuple[LiveSessionRecord, ...],
    tool_name: LiveToolName,
) -> bool:
    return any(
        call.accepted and call.tool_name == tool_name.value
        for session in sessions
        for call in session.tool_calls
    )


def _is_infrastructure_failure(record: LiveSessionRecord) -> bool:
    return record.timeout or record.rate_limit or record.provider_error
