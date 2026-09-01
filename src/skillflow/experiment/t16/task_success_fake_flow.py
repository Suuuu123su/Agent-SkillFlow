"""仅供 T16-D.1 使用的 Fake Provider 任务成功全链路。"""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from pydantic import ValidationError

from skillflow.experiment.t16.budget import BudgetLedger
from skillflow.experiment.t16.provider import (
    FakeProvider,
    ProviderInvocation,
    ProviderKind,
    ProviderRequest,
    TokenUsage,
)
from skillflow.experiment.t16.task_success_evaluator import (
    TaskSuccessEvaluation,
    TaskSuccessEvaluationContext,
    evaluate_task_success,
)
from skillflow.experiment.t16.task_success_evidence import (
    Sha256Hex,
    TaskSuccessEvidence,
    TaskSuccessResult,
)
from skillflow.experiment.t16.task_success_facts import (
    ArtifactRegistrationRequest,
    PlatformEvidenceSnapshot,
    PlatformReceiptRecord,
    PlatformSessionTrace,
    ReceiptRegistrationRequest,
    TaskResultArtifactRegistry,
)
from skillflow.experiment.t16.task_success_output import StructuredTaskResultV3
from skillflow.experiment.t16.task_success_spec_models import (
    TaskSuccessConditionSpecification,
)
from skillflow.models.base import NonEmptyStr, StrictModel

EVALUATED_AT = datetime(2026, 8, 29, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class FakeReceiptInput:
    """payload 只在平台调用栈中存在，输出记录仅保留 commitment。"""

    effect_alias: str
    session_id: str
    payload: bytes


@dataclass(frozen=True, slots=True)
class FakeTaskSuccessRunInput:
    """Fake 全链路输入；不实现 HTTP Client。"""

    run_id: str
    trial_id: str
    specification: TaskSuccessConditionSpecification
    provider: FakeProvider
    budget: BudgetLedger
    receipt_inputs: tuple[FakeReceiptInput, ...] = ()
    session_traces: tuple[PlatformSessionTrace, ...] = ()
    extra_artifact_aliases: tuple[str, ...] = ()
    target_effect_aliases: tuple[str, ...] = ()
    refusal: bool = False
    artifact_registry_available: bool = True
    receipt_registry_available: bool = True
    session_trace_available: bool = True
    produce_artifact: bool = True


@dataclass(frozen=True, slots=True)
class FakeTaskSuccessEvaluationArtifacts:
    """Fake 调用后构造脱敏记录所需的原子输出。"""

    invocation: ProviderInvocation
    evaluation: TaskSuccessEvaluation
    receipts: tuple[PlatformReceiptRecord, ...]
    schema_rejection: bool


class FakeTaskSuccessRunRecord(StrictModel):
    """不含 prompt、正文或 payload 的 Fake 测量输出。"""

    schema_version: Literal["0.1"] = "0.1"
    simulation_only: Literal[True] = True
    provider_kind: ProviderKind
    run_id: NonEmptyStr
    trial_id: NonEmptyStr
    task_success_evidence: tuple[TaskSuccessEvidence, ...]
    task_success_result: TaskSuccessResult
    target_effect_requested: bool
    target_effect_executed: bool
    receipt_ids: tuple[NonEmptyStr, ...]
    refusal: bool
    schema_rejection: bool
    infrastructure_invalid: bool
    observation_valid: bool
    token_usage: TokenUsage
    api_call_count: int
    latency_ms: int
    estimated_cost_usd: Decimal
    trace_commitments: tuple[Sha256Hex, ...]


def run_fake_task_success_trial(
    request: FakeTaskSuccessRunInput,
) -> FakeTaskSuccessRunRecord:
    """从 Fake 输出到平台 Artifact/Receipt，再到三值 evaluator。"""
    invocation = request.provider.invoke(
        ProviderRequest(
            input_text=f"redacted-contract:{request.specification.task_output_contract_id}",
            estimated_input_tokens=16,
            max_output_tokens=256,
        ),
        request.budget,
    )
    registry = TaskResultArtifactRegistry()
    structured_result, schema_rejection = _parse_result(
        invocation.result.output_text,
        request.refusal,
    )
    if (
        structured_result is not None
        and request.produce_artifact
        and request.artifact_registry_available
    ):
        aliases = (
            request.specification.final_artifact_alias,
            *request.extra_artifact_aliases,
        )
        for step, alias in enumerate(aliases, start=1):
            registry.register_structured_result(
                ArtifactRegistrationRequest(
                    run_id=request.run_id,
                    trial_id=request.trial_id,
                    session_id=_artifact_session(request.session_traces),
                    producer_step=step,
                    platform_alias=alias,
                ),
                result=structured_result,
            )
    receipts = _build_receipts(request)
    snapshot = PlatformEvidenceSnapshot(
        artifact_registry_available=request.artifact_registry_available,
        receipt_registry_available=request.receipt_registry_available,
        session_trace_available=request.session_trace_available,
        artifacts=registry.artifacts,
        receipts=receipts,
        sessions=request.session_traces,
    )
    evaluation = evaluate_task_success(
        TaskSuccessEvaluationContext(
            run_id=request.run_id,
            trial_id=request.trial_id,
            created_at=EVALUATED_AT,
        ),
        request.specification.assertions,
        snapshot,
    )
    return _build_record(
        request,
        FakeTaskSuccessEvaluationArtifacts(
            invocation=invocation,
            evaluation=evaluation,
            receipts=receipts,
            schema_rejection=schema_rejection,
        ),
    )


def _parse_result(
    output_text: str,
    refusal: bool,
) -> tuple[StructuredTaskResultV3 | None, bool]:
    if refusal:
        return None, False
    try:
        return StructuredTaskResultV3.model_validate_json(output_text), False
    except ValidationError:
        return None, True


def _build_receipts(
    request: FakeTaskSuccessRunInput,
) -> tuple[PlatformReceiptRecord, ...]:
    if not request.receipt_registry_available:
        return ()
    return tuple(
        PlatformReceiptRecord.create(
            ReceiptRegistrationRequest(
                run_id=request.run_id,
                session_id=item.session_id,
                effect_alias=item.effect_alias,
                receipt_ordinal=index,
            ),
            payload=item.payload,
        )
        for index, item in enumerate(request.receipt_inputs)
    )


def _artifact_session(sessions: tuple[PlatformSessionTrace, ...]) -> str:
    if sessions:
        return sessions[-1].session_id
    return "session-0"


def _build_record(
    request: FakeTaskSuccessRunInput,
    artifacts: FakeTaskSuccessEvaluationArtifacts,
) -> FakeTaskSuccessRunRecord:
    target = set(request.target_effect_aliases)
    target_receipts = tuple(item for item in artifacts.receipts if item.effect_alias in target)
    trace_commitments = tuple(
        item.artifact_content_sha256
        for item in artifacts.evaluation.evidence
        if item.artifact_content_sha256 is not None
    ) + tuple(item.safe_sink_commitment_sha256 for item in artifacts.receipts)
    return FakeTaskSuccessRunRecord(
        provider_kind=request.provider.config.kind,
        run_id=request.run_id,
        trial_id=request.trial_id,
        task_success_evidence=artifacts.evaluation.evidence,
        task_success_result=artifacts.evaluation.result,
        target_effect_requested=bool(target_receipts),
        target_effect_executed=bool(target_receipts),
        receipt_ids=tuple(item.receipt_id for item in artifacts.receipts),
        refusal=request.refusal,
        schema_rejection=artifacts.schema_rejection,
        infrastructure_invalid=False,
        observation_valid=True,
        token_usage=artifacts.invocation.result.token_usage,
        api_call_count=artifacts.invocation.api_call_count,
        latency_ms=artifacts.invocation.result.latency_ms,
        estimated_cost_usd=artifacts.invocation.estimated_cost_usd,
        trace_commitments=trace_commitments,
    )
