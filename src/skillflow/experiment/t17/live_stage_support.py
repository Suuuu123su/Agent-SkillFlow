"""T17 Live Stage 的失败分类、进度与预检绑定辅助。"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from skillflow.experiment.errors import ExperimentCommandError
from skillflow.experiment.t16.budget import BudgetExceededError
from skillflow.experiment.t16.live_record_builders import zero_usage
from skillflow.experiment.t17.live_attempt_models import (
    T17LiveFailureKind,
    T17LivePreflightManifest,
    T17LiveTerminalStatus,
    T17ProviderFailureDiagnostic,
)
from skillflow.experiment.t17.live_journal_models import (
    T17LiveJournalError,
    T17ModelRevisionDriftError,
)
from skillflow.experiment.t17.live_matrix import T17LiveMatrix
from skillflow.experiment.t17.live_preflight import (
    T17LivePreflightPaths,
    canonical_sha256,
    verify_live_preflight,
)
from skillflow.experiment.t17.live_reference_client import (
    OpenAIReferenceModelClient,
    ReferenceDecisionSchemaError,
    ReferenceLiveTelemetry,
    ReferenceProviderError,
    ReferenceRunStateError,
    T17ApprovedLiveConfig,
)
from skillflow.experiment.t17.live_result_store import T17LiveResultStore
from skillflow.experiment.t17.live_unit_execution import T17LiveUnitExecutionError
from skillflow.experiment.t17.observation_models import ObservationBindingError
from skillflow.experiment.t17.reference_backend import ReferenceDecisionError
from skillflow.experiment.t17.task_evidence import TaskEvidenceBuildError
from skillflow.validation import DocumentValidationError

HTTP_SERVER_ERROR_MIN = 500


@dataclass(frozen=True, slots=True)
class T17FailureClassification:
    """一个异常对应的封闭失败类型、终态和安全详情。"""

    kind: T17LiveFailureKind
    status: T17LiveTerminalStatus
    detail: str
    diagnostic: T17ProviderFailureDiagnostic | None = None


class T17LiveStageBindingError(RuntimeError):
    """执行配置没有绑定当前 preflight。"""

    def __str__(self) -> str:
        """返回稳定诊断。"""
        return "live_stage_preflight_binding_invalid"


@dataclass(frozen=True, slots=True)
class T17LiveProgressEvent:
    """只含计数、失败、Token 和费用的安全进度。"""

    completed_units: int
    scheduled_units: int
    failed_units: int
    api_call_count: int
    total_tokens: int
    estimated_cost_usd: str
    conservative_reserved_usd: str


class T17LiveProgressSink(Protocol):
    """CLI 与测试共享的安全进度输出边界。"""

    def __call__(self, event: T17LiveProgressEvent) -> None:
        """消费不含 Prompt、响应与凭据的进度。"""
        ...


def classify_live_failure(error: Exception) -> T17FailureClassification:
    """不保存异常正文，只保留预注册失败桶与安全字段。"""
    kind = T17LiveFailureKind.INFRASTRUCTURE
    status = T17LiveTerminalStatus.INCOMPLETE
    detail = error.__class__.__name__
    diagnostic = None
    if isinstance(error, BudgetExceededError):
        kind = T17LiveFailureKind.BUDGET
        detail = str(error)
    elif isinstance(error, T17ModelRevisionDriftError):
        kind = T17LiveFailureKind.MODEL_REVISION
        status = T17LiveTerminalStatus.FAILED
        detail = str(error)
    elif isinstance(error, ReferenceDecisionSchemaError) and error.detail.startswith(
        "response_incomplete:"
    ):
        detail = error.detail
    elif isinstance(error, ReferenceDecisionSchemaError):
        kind = (
            T17LiveFailureKind.MODEL_REVISION
            if error.detail == "model_revision_changed"
            else T17LiveFailureKind.SCHEMA
        )
        status = T17LiveTerminalStatus.FAILED
        detail = error.detail
    elif isinstance(error, ReferenceDecisionError):
        kind = T17LiveFailureKind.SCHEMA
        status = T17LiveTerminalStatus.FAILED
        detail = error.reason
    elif isinstance(error, ReferenceProviderError):
        kind = (
            T17LiveFailureKind.PROVIDER_4XX
            if error.status_code is not None and error.status_code < HTTP_SERVER_ERROR_MIN
            else T17LiveFailureKind.INFRASTRUCTURE
        )
        detail = str(error)
        diagnostic = T17ProviderFailureDiagnostic(
            status_code=error.status_code,
            provider_type=error.provider_type,
            provider_code=error.provider_code,
            provider_param=error.provider_param,
        )
    elif isinstance(
        error,
        (
            ObservationBindingError,
            TaskEvidenceBuildError,
            T17LiveUnitExecutionError,
        ),
    ):
        kind = T17LiveFailureKind.EVIDENCE_BINDING
        status = T17LiveTerminalStatus.FAILED
        detail = str(error)
    elif isinstance(
        error,
        (
            DocumentValidationError,
            ExperimentCommandError,
            T17LiveJournalError,
            OSError,
        ),
    ):
        detail = error.__class__.__name__
    return T17FailureClassification(kind, status, detail, diagnostic)


def end_run_or_zero(client: OpenAIReferenceModelClient) -> ReferenceLiveTelemetry:
    """失败清理时返回 Run 增量；生命周期已坏则明确使用零客户端值。"""
    try:
        return client.end_run()
    except ReferenceRunStateError:
        return ReferenceLiveTelemetry(
            api_call_count=0,
            response_count=0,
            agent_step_count=0,
            retry_count=0,
            refusal_count=0,
            no_call_count=0,
            token_usage=zero_usage(),
            latency_ms=0,
            estimated_cost_usd=Decimal(0),
            conservative_reserved_usd=Decimal(0),
        )


def emit_live_progress(
    matrix: T17LiveMatrix,
    results: T17LiveResultStore,
    progress: T17LiveProgressSink | None,
) -> None:
    """向可调用 sink 发送不含正文的累计进度。"""
    if progress is None:
        return
    records = results.records
    total_tokens = sum(
        item.telemetry.token_usage.input_tokens
        + item.telemetry.token_usage.output_tokens
        + item.telemetry.token_usage.reasoning_tokens
        for item in records
    )
    event = T17LiveProgressEvent(
        completed_units=sum(
            item.terminal_status is T17LiveTerminalStatus.COMPLETED for item in records
        ),
        scheduled_units=matrix.scheduled_core_trials + matrix.scheduled_replay_pairs,
        failed_units=sum(
            item.terminal_status is not T17LiveTerminalStatus.COMPLETED for item in records
        ),
        api_call_count=sum(item.telemetry.api_call_count for item in records),
        total_tokens=total_tokens,
        estimated_cost_usd=str(
            sum(
                (item.telemetry.estimated_cost_usd for item in records),
                start=Decimal(0),
            )
        ),
        conservative_reserved_usd=str(
            sum(
                (item.telemetry.conservative_reserved_usd for item in records),
                start=Decimal(0),
            )
        ),
    )
    progress(event)


def require_execution_binding(
    config: T17ApprovedLiveConfig,
    matrix: T17LiveMatrix,
    preflight: T17LivePreflightManifest,
    paths: T17LivePreflightPaths,
) -> None:
    """阻止未绑定当前预检的配置进入网络调用路径。"""
    if (
        preflight.stage is not matrix.stage
        or preflight.matrix_id != matrix.id
        or preflight.approved_config_sha256 != canonical_sha256(config.model_dump(mode="json"))
    ):
        raise T17LiveStageBindingError
    verify_live_preflight(paths, config, preflight)
