from skillflow.experiment.t17.live_attempt_models import (
    T17LiveFailureKind,
    T17LiveTerminalStatus,
)
from skillflow.experiment.t17.live_journal_models import (
    T17LiveJournalError,
    T17LiveJournalErrorCode,
    T17ModelRevisionDriftError,
)
from skillflow.experiment.t17.live_preflight import (
    T17LivePreflightError,
    T17LivePreflightErrorCode,
)
from skillflow.experiment.t17.live_reference_client import (
    ReferenceDecisionSchemaError,
    ReferenceProviderError,
    ReferenceRunStateError,
)
from skillflow.experiment.t17.live_result_store import (
    T17LiveResultStoreError,
    T17LiveResultStoreErrorCode,
)
from skillflow.experiment.t17.live_stage_support import (
    T17LiveStageBindingError,
    classify_live_failure,
)
from skillflow.experiment.t17.live_unit_execution import T17LiveUnitExecutionError
from skillflow.experiment.t17.observation_models import ObservationBindingError
from skillflow.experiment.t17.reference_backend import ReferenceDecisionError
from skillflow.experiment.t17.task_evidence import TaskEvidenceBuildError
from skillflow.instrumentation.errors import UnsupportedStepError
from skillflow.oracle.errors import OracleInvariantError


def test_live_custom_errors_preserve_exception_runtime_state() -> None:
    errors = (
        T17LiveJournalError(T17LiveJournalErrorCode.HASH_INVALID),
        T17ModelRevisionDriftError("expected", "actual"),
        T17LivePreflightError(T17LivePreflightErrorCode.CONFIG_DRIFT),
        T17LiveResultStoreError(T17LiveResultStoreErrorCode.APPEND_FAILED),
        T17LiveStageBindingError(),
        T17LiveUnitExecutionError("unit-1", "evidence_missing"),
        ReferenceDecisionSchemaError("schema"),
        ReferenceProviderError("provider_error"),
        ReferenceRunStateError("run_state"),
        ReferenceDecisionError("fixture", "action", "invalid"),
        TaskEvidenceBuildError("run-1"),
        ObservationBindingError("decision-1", "missing"),
        OracleInvariantError("expected_origins", "missing effect"),
        UnsupportedStepError("step-1", "required input missing"),
    )

    for error in errors:
        error.__traceback__ = None

    assert all(error.__traceback__ is None for error in errors)


def test_incomplete_response_is_infrastructure_not_model_schema() -> None:
    classified = classify_live_failure(
        ReferenceDecisionSchemaError("response_incomplete:max_output_tokens")
    )

    assert classified.kind is T17LiveFailureKind.INFRASTRUCTURE
    assert classified.status is T17LiveTerminalStatus.INCOMPLETE
    assert classified.detail == "response_incomplete:max_output_tokens"


def test_oracle_invariant_is_a_terminal_evidence_binding_failure() -> None:
    classified = classify_live_failure(OracleInvariantError("expected_origins", "missing effect"))

    assert classified.kind is T17LiveFailureKind.EVIDENCE_BINDING
    assert classified.status is T17LiveTerminalStatus.FAILED
    assert "expected_origins" in classified.detail


def test_missing_step_is_a_terminal_evidence_binding_failure() -> None:
    classified = classify_live_failure(
        UnsupportedStepError("step-1", "required input missing: artifact-x")
    )

    assert classified.kind is T17LiveFailureKind.EVIDENCE_BINDING
    assert classified.status is T17LiveTerminalStatus.FAILED
    assert "required input missing" in classified.detail
