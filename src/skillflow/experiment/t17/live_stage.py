"""T17 Live 单阶段调度、失败分类、Raw 持久化与阶段门。"""

from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from skillflow.experiment.errors import ExperimentCommandError
from skillflow.experiment.io import write_json_model
from skillflow.experiment.layout import ExperimentLayout
from skillflow.experiment.t16.budget import BudgetExceededError
from skillflow.experiment.t17.live_attempt_models import (
    T17LivePreflightManifest,
    T17LiveStageSummary,
    T17LiveTerminalStatus,
    T17LiveUnitKind,
    T17LiveUnitRecord,
)
from skillflow.experiment.t17.live_journal import (
    T17LiveUsageJournal,
    T17LiveUsageTracker,
)
from skillflow.experiment.t17.live_journal_models import (
    T17LiveJournalBinding,
    T17LiveJournalError,
    T17ModelRevisionDriftError,
)
from skillflow.experiment.t17.live_matrix import T17LiveMatrix, T17LiveTrial, load_live_matrix
from skillflow.experiment.t17.live_preflight import T17LivePreflightPaths
from skillflow.experiment.t17.live_reference_client import (
    OpenAIReferenceModelClient,
    ReferenceDecisionSchemaError,
    ReferenceProviderError,
    T17ApprovedLiveConfig,
)
from skillflow.experiment.t17.live_result_store import T17LiveResultStore
from skillflow.experiment.t17.live_stage_support import (
    T17LiveProgressSink,
    classify_live_failure,
    emit_live_progress,
    end_run_or_zero,
    require_execution_binding,
)
from skillflow.experiment.t17.live_summary import (
    T17LiveSummaryRequest,
    build_live_stage_summary,
)
from skillflow.experiment.t17.live_unit_execution import (
    T17CoreExecution,
    T17LiveExecutionContext,
    T17LiveExecutionSetup,
    T17LiveUnitExecutionError,
    create_live_execution_context,
    execute_live_core,
    execute_live_replay,
    replay_unit_id,
)
from skillflow.experiment.t17.observation_models import ObservationBindingError
from skillflow.experiment.t17.reference_backend import ReferenceDecisionError
from skillflow.experiment.t17.scenario_registry import (
    load_scenario_measurement_registry,
)
from skillflow.experiment.t17.task_evidence import (
    T17TaskSuccessEvidence,
    TaskEvidenceBuildError,
)
from skillflow.models.matrix import ExperimentMatrix
from skillflow.models.references import ArtifactAliasRef
from skillflow.validation import DocumentValidationError, validate_yaml_document


@dataclass(frozen=True, slots=True)
class T17LiveStageRequest:
    """一个已经完成非秘密预算批准和预检的阶段执行请求。"""

    project_root: Path
    attempt_root: Path
    matrix_path: Path
    base_matrix_path: Path
    registry_path: Path
    preflight_path: Path
    preflight_inputs: T17LivePreflightPaths
    config: T17ApprovedLiveConfig


@dataclass(frozen=True, slots=True)
class T17LiveStageResult:
    """本次不可变 Attempt 的 Raw 根与阶段摘要。"""

    attempt_root: Path
    summary: T17LiveStageSummary


@dataclass(frozen=True, slots=True)
class _StageRuntime:
    """单阶段调度中共享且不变的执行依赖。"""

    context: T17LiveExecutionContext
    matrix: T17LiveMatrix
    client: OpenAIReferenceModelClient
    journal: T17LiveUsageJournal
    results: T17LiveResultStore


def execute_live_stage(
    request: T17LiveStageRequest,
    client: OpenAIReferenceModelClient,
    progress: T17LiveProgressSink | None = None,
) -> T17LiveStageResult:
    """按静态顺序执行核心 Trial 和所需 Replay；任一硬失败立即停止。"""
    matrix = load_live_matrix(request.matrix_path)
    registry = load_scenario_measurement_registry(request.registry_path)
    base_matrix = validate_yaml_document(request.base_matrix_path, ExperimentMatrix)
    preflight = T17LivePreflightManifest.model_validate_json(
        request.preflight_path.read_text(encoding="utf-8")
    )
    require_execution_binding(
        request.config,
        matrix,
        preflight,
        request.preflight_inputs,
    )
    layout = ExperimentLayout.create(request.attempt_root / "raw")
    journal = T17LiveUsageJournal(
        request.attempt_root / "actual-usage-journal.jsonl",
        T17LiveJournalBinding(
            phase_contract_sha256=preflight.phase_contract_sha256,
            approved_config_sha256=preflight.approved_config_sha256,
            stage=matrix.stage,
            model_id=matrix.provider.model_id,
            model_revision=matrix.provider.model_revision,
        ),
    )
    results = T17LiveResultStore(request.attempt_root / "trial-results.jsonl")
    journal.open_new()
    results.open_new()
    context = create_live_execution_context(
        T17LiveExecutionSetup(
            request.project_root,
            request.attempt_root,
            layout,
            base_matrix,
            matrix,
            registry,
            client,
        )
    )
    runtime = _StageRuntime(context, matrix, client, journal, results)
    stop_detail: str | None = None
    for trial in matrix.trials:
        core, failure = _execute_core(runtime, trial)
        emit_live_progress(matrix, results, progress)
        if failure is not None:
            stop_detail = failure
            break
        if core is None:
            raise T17LiveUnitExecutionError(
                trial.trial_id,
                "core_missing_without_failure",
            )
        for target in trial.replay_target_aliases:
            failure = _execute_replay(runtime, trial, target, core)
            emit_live_progress(matrix, results, progress)
            if failure is not None:
                stop_detail = failure
                break
        if stop_detail is not None:
            break
    summary = build_live_stage_summary(
        T17LiveSummaryRequest(
            request.attempt_root,
            matrix,
            registry,
            results.records,
            stop_detail,
        )
    )
    write_json_model(request.attempt_root / "live-summary.json", summary)
    return T17LiveStageResult(request.attempt_root, summary)


def _execute_core(
    runtime: _StageRuntime,
    trial: T17LiveTrial,
) -> tuple[T17CoreExecution | None, str | None]:
    tracker = runtime.journal.start_unit(
        trial.trial_id,
        trial.trial_id,
        T17LiveUnitKind.CORE,
    )
    runtime.client.begin_run(tracker)
    try:
        core = execute_live_core(runtime.context, trial)
        task = _require_task_evidence(core, trial)
    except (
        BudgetExceededError,
        T17ModelRevisionDriftError,
        ReferenceDecisionSchemaError,
        ReferenceDecisionError,
        ReferenceProviderError,
        ObservationBindingError,
        TaskEvidenceBuildError,
        T17LiveUnitExecutionError,
        DocumentValidationError,
        ExperimentCommandError,
        T17LiveJournalError,
        ValidationError,
        OSError,
    ) as error:
        failure = _record_failure(runtime, trial, trial.trial_id, tracker, error)
        return None, failure
    telemetry = tracker.finalize(
        runtime.client.end_run(),
        T17LiveTerminalStatus.COMPLETED,
    )
    runtime.results.append(
        T17LiveUnitRecord(
            sequence=runtime.results.next_sequence,
            stage=runtime.matrix.stage,
            unit_id=trial.trial_id,
            trial_id=trial.trial_id,
            unit_kind=T17LiveUnitKind.CORE,
            variant=trial.variant,
            source_variant=trial.source_variant,
            enforcement_mode=trial.enforcement_mode,
            scenario_id=trial.scenario_id,
            semantic_instance_id=trial.semantic_instance_id,
            semantic_template_id=trial.semantic_template_id,
            repeat_index=trial.repeat_index,
            terminal_status=T17LiveTerminalStatus.COMPLETED,
            telemetry=telemetry,
            run_ids=(core.executed.result.run_id,),
            replay_ids=(),
            task_success=task.task_success,
            safe_task_success=core.safe_task_success,
            evidence_ids=core.evidence_ids,
            artifacts=core.artifacts,
        )
    )
    return core, None


def _execute_replay(
    runtime: _StageRuntime,
    trial: T17LiveTrial,
    target: ArtifactAliasRef,
    core: T17CoreExecution,
) -> str | None:
    unit_id = replay_unit_id(trial, target)
    tracker = runtime.journal.start_unit(
        unit_id,
        trial.trial_id,
        T17LiveUnitKind.REPLAY,
    )
    runtime.client.begin_run(tracker)
    try:
        replay = execute_live_replay(runtime.context, trial, core, target)
    except (
        BudgetExceededError,
        T17ModelRevisionDriftError,
        ReferenceDecisionSchemaError,
        ReferenceDecisionError,
        ReferenceProviderError,
        ObservationBindingError,
        TaskEvidenceBuildError,
        T17LiveUnitExecutionError,
        DocumentValidationError,
        ExperimentCommandError,
        T17LiveJournalError,
        ValidationError,
        OSError,
    ) as error:
        return _record_failure(runtime, trial, unit_id, tracker, error)
    telemetry = tracker.finalize(
        runtime.client.end_run(),
        T17LiveTerminalStatus.COMPLETED,
    )
    runtime.results.append(
        T17LiveUnitRecord(
            sequence=runtime.results.next_sequence,
            stage=runtime.matrix.stage,
            unit_id=unit_id,
            trial_id=trial.trial_id,
            unit_kind=T17LiveUnitKind.REPLAY,
            variant=trial.variant,
            source_variant=trial.source_variant,
            enforcement_mode=trial.enforcement_mode,
            scenario_id=trial.scenario_id,
            semantic_instance_id=trial.semantic_instance_id,
            semantic_template_id=trial.semantic_template_id,
            repeat_index=trial.repeat_index,
            terminal_status=T17LiveTerminalStatus.COMPLETED,
            telemetry=telemetry,
            run_ids=(),
            replay_ids=(replay.report.replay_id,),
            task_success=None,
            safe_task_success=None,
            evidence_ids=replay.evidence_ids,
            artifacts=replay.artifacts,
        )
    )
    return None


def _record_failure(
    runtime: _StageRuntime,
    trial: T17LiveTrial,
    unit_id: str,
    tracker: T17LiveUsageTracker,
    error: Exception,
) -> str:
    failure = classify_live_failure(error)
    telemetry = tracker.finalize(
        end_run_or_zero(runtime.client),
        failure.status,
        failure.kind,
        failure.detail,
    )
    unit_kind = T17LiveUnitKind.CORE if unit_id == trial.trial_id else T17LiveUnitKind.REPLAY
    runtime.results.append(
        T17LiveUnitRecord(
            sequence=runtime.results.next_sequence,
            stage=runtime.matrix.stage,
            unit_id=unit_id,
            trial_id=trial.trial_id,
            unit_kind=unit_kind,
            variant=trial.variant,
            source_variant=trial.source_variant,
            enforcement_mode=trial.enforcement_mode,
            scenario_id=trial.scenario_id,
            semantic_instance_id=trial.semantic_instance_id,
            semantic_template_id=trial.semantic_template_id,
            repeat_index=trial.repeat_index,
            terminal_status=failure.status,
            failure_kind=failure.kind,
            failure_detail=failure.detail,
            telemetry=telemetry,
            run_ids=(),
            replay_ids=(),
            task_success=None,
            safe_task_success=None,
            evidence_ids=(),
            artifacts=(),
        )
    )
    return f"{failure.kind.value}:{failure.detail}"


def _require_task_evidence(
    core: T17CoreExecution,
    trial: T17LiveTrial,
) -> T17TaskSuccessEvidence:
    task = core.snapshot.task_success
    if task is None:
        raise T17LiveUnitExecutionError(trial.trial_id, "task_evidence_missing")
    return task
