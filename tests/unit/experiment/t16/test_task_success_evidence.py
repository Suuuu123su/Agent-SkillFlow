from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from skillflow.experiment.t16.task_success_assertions import (
    TASK_SUCCESS_ASSERTIONS_ADAPTER,
)
from skillflow.experiment.t16.task_success_evidence import (
    AssertionStatus,
    TaskSuccessAggregation,
    TaskSuccessEvidence,
    TaskSuccessResult,
    TaskSuccessStatus,
)


def _evidence(assertion_id: str, status: AssertionStatus) -> TaskSuccessEvidence:
    return TaskSuccessEvidence(
        evidence_id=f"evidence-{assertion_id}",
        run_id="run-1",
        trial_id="trial-1",
        session_id=None,
        assertion_id=assertion_id,
        assertion_type="artifact_exists",
        assertion_status=status,
        artifact_id=None,
        artifact_alias="artifact:summary",
        artifact_content_sha256=None,
        effect_id=None,
        receipt_id=None,
        safe_sink_commitment_sha256=None,
        expected_value_commitment_sha256=None,
        observed_value_commitment_sha256=None,
        evaluator_id="task-success-evaluator",
        evaluator_version="1.0.0",
        evidence_source="platform_artifact_registry",
        reason_code="artifact_registry_unavailable",
        created_at=datetime(2026, 8, 29, tzinfo=UTC),
    )


@pytest.mark.parametrize(
    ("statuses", "expected_success", "expected_status"),
    [
        ((AssertionStatus.PASSED, AssertionStatus.PASSED), True, TaskSuccessStatus.PASSED),
        ((AssertionStatus.PASSED, AssertionStatus.FAILED), False, TaskSuccessStatus.FAILED),
        (
            (AssertionStatus.PASSED, AssertionStatus.NOT_EVALUABLE),
            None,
            TaskSuccessStatus.NOT_EVALUABLE,
        ),
    ],
)
def test_result_aggregates_required_assertions_without_coercing_na(
    statuses: tuple[AssertionStatus, ...],
    expected_success: bool | None,
    expected_status: TaskSuccessStatus,
) -> None:
    evidence = tuple(_evidence(f"a{index}", status) for index, status in enumerate(statuses))

    result = TaskSuccessResult.from_evidence(
        TaskSuccessAggregation(
            trial_id="trial-1",
            evidence=evidence,
            evaluator_version="1.0.0",
        )
    )

    assert result.task_success is expected_success
    assert result.status is expected_status
    assert set(result.required_assertion_ids) == {"a0", "a1"}


def test_result_rejects_overlap_and_incomplete_required_partition() -> None:
    with pytest.raises(ValidationError):
        TaskSuccessResult(
            trial_id="trial-1",
            required_assertion_ids=("a", "b"),
            passed_assertion_ids=("a",),
            failed_assertion_ids=("a",),
            not_evaluable_assertion_ids=(),
            task_success=False,
            status=TaskSuccessStatus.FAILED,
            evidence_ids=("evidence-a",),
            evaluator_version="1.0.0",
        )


def test_evidence_rejects_model_claimed_source_and_malformed_sha() -> None:
    payload = _evidence("a", AssertionStatus.PASSED).model_dump(mode="json")
    payload["evidence_source"] = "model_report"
    payload["artifact_content_sha256"] = "not-a-sha"

    with pytest.raises(ValidationError):
        TaskSuccessEvidence.model_validate(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"assertion_id": "a", "assertion_type": "python_eval", "code": "True"},
        {
            "assertion_id": "a",
            "assertion_type": "artifact_exists",
            "artifact_alias": "artifact:summary",
            "code": "True",
        },
    ],
)
def test_assertion_whitelist_rejects_dynamic_code(payload: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        TASK_SUCCESS_ASSERTIONS_ADAPTER.validate_python((payload,))
