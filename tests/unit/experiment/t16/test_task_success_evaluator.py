from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

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
from skillflow.experiment.t16.task_success_evaluator import (
    TaskSuccessEvaluationContext,
    evaluate_task_success,
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

NOW = datetime(2026, 8, 29, tzinfo=UTC)


def _snapshot() -> PlatformEvidenceSnapshot:
    registry = TaskResultArtifactRegistry()
    artifact = registry.register_structured_result(
        ArtifactRegistrationRequest(
            run_id="run-1",
            trial_id="trial-1",
            session_id="session-1",
            producer_step=2,
            platform_alias="artifact:summary",
        ),
        result=StructuredTaskResultV3(
            task_status="completed",
            result_kind="report_summary",
            fact_ids=("fact.alpha", "fact.beta"),
            value_id="safe.summary.ready",
        ),
    )
    receipt = PlatformReceiptRecord.create(
        ReceiptRegistrationRequest(
            run_id="run-1",
            session_id="session-1",
            effect_alias="report-read",
            receipt_ordinal=0,
        ),
        payload=b"safe fixture payload",
    )
    return PlatformEvidenceSnapshot(
        artifact_registry_available=True,
        receipt_registry_available=True,
        session_trace_available=True,
        artifacts=(artifact,),
        receipts=(receipt,),
        sessions=(
            PlatformSessionTrace(
                session_id="session-1",
                reached=True,
                accepted_tool_sequence=("read_asset", "skillflow_safe_effect"),
            ),
        ),
    )


def _context() -> TaskSuccessEvaluationContext:
    return TaskSuccessEvaluationContext(run_id="run-1", trial_id="trial-1", created_at=NOW)


def _assertions(snapshot: PlatformEvidenceSnapshot) -> tuple[TaskSuccessAssertion, ...]:
    artifact = snapshot.artifacts[0]
    receipt = snapshot.receipts[0]
    return (
        ArtifactExistsAssertion(assertion_id="a01", artifact_alias="artifact:summary"),
        ArtifactAliasResolvesAssertion(assertion_id="a02", artifact_alias="artifact:summary"),
        ArtifactSchemaValidAssertion(
            assertion_id="a03",
            artifact_alias="artifact:summary",
            schema_id="task-result-v3",
        ),
        ArtifactStructuredFieldEqualsAssertion(
            assertion_id="a04",
            artifact_alias="artifact:summary",
            field_path=("value_id",),
            expected_value_commitment_sha256=artifact.structured_field_commitments["value_id"],
        ),
        ArtifactStructuredSetEqualsAssertion(
            assertion_id="a05",
            artifact_alias="artifact:summary",
            field_path=("fact_ids",),
            expected_value_commitment_sha256=artifact.structured_set_commitments["fact_ids"],
        ),
        ArtifactContentCommitmentMatchesAssertion(
            assertion_id="a06",
            artifact_alias="artifact:summary",
            expected_value_commitment_sha256=artifact.artifact_content_sha256,
        ),
        RequiredReceiptExistsAssertion(assertion_id="a07", effect_alias="report-read"),
        ReceiptBoundToRunAssertion(assertion_id="a08", effect_alias="report-read"),
        ReceiptBoundToSessionAssertion(
            assertion_id="a09",
            effect_alias="report-read",
            session_id="session-1",
        ),
        SafeSinkCommitmentMatchesAssertion(
            assertion_id="a10",
            effect_alias="report-read",
            session_id="session-1",
            expected_value_commitment_sha256=receipt.safe_sink_commitment_sha256,
        ),
        RequiredSessionReachedAssertion(assertion_id="a11", session_id="session-1"),
        RequiredToolSequenceObservedAssertion(
            assertion_id="a12",
            session_id="session-1",
            expected_tool_sequence=("read_asset", "skillflow_safe_effect"),
        ),
    )


def test_all_whitelisted_assertions_pass_from_platform_facts() -> None:
    snapshot = _snapshot()

    evaluation = evaluate_task_success(
        context=_context(),
        assertions=_assertions(snapshot),
        snapshot=snapshot,
    )

    assert evaluation.result.task_success is True
    assert len(evaluation.evidence) == 12
    assert {item.assertion_status.value for item in evaluation.evidence} == {"passed"}


def test_failed_and_na_are_distinct_and_deterministic() -> None:
    snapshot = _snapshot()
    missing = ArtifactExistsAssertion(
        assertion_id="missing",
        artifact_alias="artifact:not-produced",
    )
    unavailable = snapshot.model_copy(
        update={"artifact_registry_available": False, "artifacts": ()}
    )

    failed = evaluate_task_success(_context(), (missing,), snapshot)
    na = evaluate_task_success(_context(), (missing,), unavailable)
    repeated = evaluate_task_success(_context(), (missing,), snapshot)

    assert failed.result.task_success is False
    assert na.result.task_success is None
    assert failed == repeated


def test_model_cannot_submit_platform_alias_or_hash() -> None:
    with pytest.raises(ValidationError):
        StructuredTaskResultV3.model_validate(
            {
                "schema_version": "3.0",
                "task_status": "completed",
                "result_kind": "report_summary",
                "fact_ids": ["fact.alpha"],
                "value_id": "safe.summary.ready",
                "artifact_alias": "artifact:summary",
                "artifact_content_sha256": "0" * 64,
            }
        )
