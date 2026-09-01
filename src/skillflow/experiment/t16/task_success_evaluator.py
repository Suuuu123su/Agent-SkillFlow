"""版本化、确定性的 TaskSuccessEvidence evaluator。"""

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import assert_never

from pydantic_core import PydanticCustomError

from skillflow.experiment.t16.task_success_artifact_checks import (
    check_artifact_assertion,
)
from skillflow.experiment.t16.task_success_assertions import (
    ArtifactAliasResolvesAssertion,
    ArtifactContentCommitmentMatchesAssertion,
    ArtifactExistsAssertion,
    ArtifactSchemaValidAssertion,
    ArtifactStructuredFieldEqualsAssertion,
    ArtifactStructuredSetEqualsAssertion,
    ReceiptBoundToRunAssertion,
    ReceiptBoundToSessionAssertion,
    RequiredReceiptExistsAssertion,
    RequiredSessionReachedAssertion,
    RequiredToolSequenceObservedAssertion,
    SafeSinkCommitmentMatchesAssertion,
    TaskSuccessAssertion,
)
from skillflow.experiment.t16.task_success_evidence import (
    TASK_SUCCESS_EVALUATOR_ID,
    TASK_SUCCESS_EVALUATOR_VERSION,
    TaskSuccessAggregation,
    TaskSuccessEvidence,
    TaskSuccessResult,
)
from skillflow.experiment.t16.task_success_facts import PlatformEvidenceSnapshot
from skillflow.experiment.t16.task_success_observations import AssertionObservation
from skillflow.experiment.t16.task_success_runtime_checks import check_runtime_assertion


@dataclass(frozen=True, slots=True)
class TaskSuccessEvaluation:
    """一条 Trial 的 Evidence 与 Result 原子输出。"""

    evidence: tuple[TaskSuccessEvidence, ...]
    result: TaskSuccessResult


@dataclass(frozen=True, slots=True)
class TaskSuccessEvaluationContext:
    """一次确定性评估共享的 Run、Trial 与时间身份。"""

    run_id: str
    trial_id: str
    created_at: datetime


def evaluate_task_success(
    context: TaskSuccessEvaluationContext,
    assertions: tuple[TaskSuccessAssertion, ...],
    snapshot: PlatformEvidenceSnapshot,
) -> TaskSuccessEvaluation:
    """只依据平台快照执行白名单断言并进行三值聚合。"""
    assertion_ids = tuple(item.assertion_id for item in assertions)
    if len(set(assertion_ids)) != len(assertion_ids):
        raise PydanticCustomError(
            "t16_task_success_assertion_duplicate",
            "同一 Trial 的 assertion_id 不得重复",
        )
    evidence = tuple(
        _to_evidence(
            context,
            assertion,
            _dispatch(assertion, snapshot, context.run_id),
        )
        for assertion in assertions
    )
    required_ids = tuple(item.assertion_id for item in assertions if item.required)
    result = TaskSuccessResult.from_evidence(
        TaskSuccessAggregation(
            trial_id=context.trial_id,
            evidence=evidence,
            evaluator_version=TASK_SUCCESS_EVALUATOR_VERSION,
            required_assertion_ids=required_ids,
        )
    )
    return TaskSuccessEvaluation(evidence=evidence, result=result)


def _dispatch(
    assertion: TaskSuccessAssertion,
    snapshot: PlatformEvidenceSnapshot,
    run_id: str,
) -> AssertionObservation:
    match assertion:
        case (
            ArtifactExistsAssertion()
            | ArtifactAliasResolvesAssertion()
            | ArtifactSchemaValidAssertion()
            | ArtifactStructuredFieldEqualsAssertion()
            | ArtifactStructuredSetEqualsAssertion()
            | ArtifactContentCommitmentMatchesAssertion()
        ):
            return check_artifact_assertion(assertion, snapshot)
        case (
            RequiredReceiptExistsAssertion()
            | ReceiptBoundToRunAssertion()
            | ReceiptBoundToSessionAssertion()
            | SafeSinkCommitmentMatchesAssertion()
            | RequiredSessionReachedAssertion()
            | RequiredToolSequenceObservedAssertion()
        ):
            return check_runtime_assertion(assertion, snapshot, run_id)
        case unreachable:
            assert_never(unreachable)


def _to_evidence(
    context: TaskSuccessEvaluationContext,
    assertion: TaskSuccessAssertion,
    observation: AssertionObservation,
) -> TaskSuccessEvidence:
    material = (
        f"{TASK_SUCCESS_EVALUATOR_VERSION}:{context.run_id}:"
        f"{context.trial_id}:{assertion.assertion_id}"
    )
    evidence_id = f"tse-{hashlib.sha256(material.encode()).hexdigest()[:24]}"
    return TaskSuccessEvidence(
        evidence_id=evidence_id,
        run_id=context.run_id,
        trial_id=context.trial_id,
        session_id=observation.session_id,
        assertion_id=assertion.assertion_id,
        assertion_type=assertion.assertion_type,
        assertion_status=observation.status,
        artifact_id=observation.artifact_id,
        artifact_alias=observation.artifact_alias,
        artifact_content_sha256=observation.artifact_content_sha256,
        effect_id=observation.effect_id,
        receipt_id=observation.receipt_id,
        safe_sink_commitment_sha256=observation.safe_sink_commitment_sha256,
        expected_value_commitment_sha256=(observation.expected_value_commitment_sha256),
        observed_value_commitment_sha256=(observation.observed_value_commitment_sha256),
        evaluator_id=TASK_SUCCESS_EVALUATOR_ID,
        evaluator_version=TASK_SUCCESS_EVALUATOR_VERSION,
        evidence_source=observation.source,
        reason_code=observation.reason,
        created_at=context.created_at,
    )
