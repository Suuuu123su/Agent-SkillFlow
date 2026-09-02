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
from skillflow.experiment.t17.live_stage_support import T17LiveStageBindingError
from skillflow.experiment.t17.live_unit_execution import T17LiveUnitExecutionError
from skillflow.experiment.t17.observation_models import ObservationBindingError
from skillflow.experiment.t17.reference_backend import ReferenceDecisionError
from skillflow.experiment.t17.task_evidence import TaskEvidenceBuildError


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
    )

    for error in errors:
        error.__traceback__ = None

    assert all(error.__traceback__ is None for error in errors)
