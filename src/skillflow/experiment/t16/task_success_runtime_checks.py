"""Receipt、Safe Sink 与 Session 类白名单断言检查器。"""

from skillflow.experiment.t16.task_success_assertions import (
    ReceiptBoundToRunAssertion,
    ReceiptBoundToSessionAssertion,
    RequiredReceiptExistsAssertion,
    RequiredSessionReachedAssertion,
    RequiredToolSequenceObservedAssertion,
    SafeSinkCommitmentMatchesAssertion,
)
from skillflow.experiment.t16.task_success_evidence import (
    AssertionStatus,
    EvidenceReason,
    EvidenceSource,
)
from skillflow.experiment.t16.task_success_facts import (
    PlatformEvidenceSnapshot,
    PlatformReceiptRecord,
)
from skillflow.experiment.t16.task_success_observations import AssertionObservation

RuntimeAssertion = (
    RequiredReceiptExistsAssertion
    | ReceiptBoundToRunAssertion
    | ReceiptBoundToSessionAssertion
    | SafeSinkCommitmentMatchesAssertion
    | RequiredSessionReachedAssertion
    | RequiredToolSequenceObservedAssertion
)


def check_runtime_assertion(
    assertion: RuntimeAssertion,
    snapshot: PlatformEvidenceSnapshot,
    run_id: str,
) -> AssertionObservation:
    """检查平台 Receipt 或 Session Trace，不使用模型陈述。"""
    if isinstance(
        assertion,
        (RequiredSessionReachedAssertion, RequiredToolSequenceObservedAssertion),
    ):
        return _check_session_assertion(assertion, snapshot)
    return _check_receipt_assertion(assertion, snapshot, run_id)


def _check_receipt_assertion(
    assertion: (
        RequiredReceiptExistsAssertion
        | ReceiptBoundToRunAssertion
        | ReceiptBoundToSessionAssertion
        | SafeSinkCommitmentMatchesAssertion
    ),
    snapshot: PlatformEvidenceSnapshot,
    run_id: str,
) -> AssertionObservation:
    if not snapshot.receipt_registry_available:
        return AssertionObservation(
            AssertionStatus.NOT_EVALUABLE,
            EvidenceSource.PLATFORM_EFFECT_RECEIPT,
            EvidenceReason.RECEIPT_REGISTRY_UNAVAILABLE,
            session_id=getattr(assertion, "session_id", None),
        )
    candidates = tuple(
        item for item in snapshot.receipts if item.effect_alias == assertion.effect_alias
    )
    if isinstance(assertion, RequiredReceiptExistsAssertion):
        if assertion.session_id is not None:
            candidates = tuple(
                item for item in candidates if item.session_id == assertion.session_id
            )
        return _receipt_presence(candidates, assertion.session_id)
    if isinstance(assertion, ReceiptBoundToRunAssertion):
        return _receipt_match(
            candidates,
            next((item for item in candidates if item.run_id == run_id), None),
            EvidenceReason.RECEIPT_RUN_MISMATCH,
        )
    if isinstance(assertion, ReceiptBoundToSessionAssertion):
        match = next(
            (
                item
                for item in candidates
                if item.run_id == run_id and item.session_id == assertion.session_id
            ),
            None,
        )
        return _receipt_match(candidates, match, EvidenceReason.RECEIPT_SESSION_MISMATCH)
    scoped = tuple(
        item
        for item in candidates
        if item.run_id == run_id
        and (assertion.session_id is None or item.session_id == assertion.session_id)
    )
    match = next(
        (
            item
            for item in scoped
            if item.safe_sink_commitment_sha256 == assertion.expected_value_commitment_sha256
        ),
        None,
    )
    observed = scoped[0] if scoped else None
    return _safe_sink_match(assertion.expected_value_commitment_sha256, observed, match)


def _receipt_presence(
    candidates: tuple[PlatformReceiptRecord, ...],
    session_id: str | None,
) -> AssertionObservation:
    if not candidates:
        return AssertionObservation(
            AssertionStatus.FAILED,
            EvidenceSource.PLATFORM_EFFECT_RECEIPT,
            EvidenceReason.RECEIPT_MISSING,
            session_id=session_id,
        )
    return _receipt_observation(candidates[0])


def _receipt_match(
    candidates: tuple[PlatformReceiptRecord, ...],
    match: PlatformReceiptRecord | None,
    mismatch_reason: EvidenceReason,
) -> AssertionObservation:
    if match is not None:
        return _receipt_observation(match)
    return AssertionObservation(
        AssertionStatus.FAILED,
        EvidenceSource.PLATFORM_EFFECT_RECEIPT,
        mismatch_reason if candidates else EvidenceReason.RECEIPT_MISSING,
    )


def _receipt_observation(receipt: PlatformReceiptRecord) -> AssertionObservation:
    return AssertionObservation(
        AssertionStatus.PASSED,
        EvidenceSource.PLATFORM_EFFECT_RECEIPT,
        EvidenceReason.ASSERTION_PASSED,
        session_id=receipt.session_id,
        effect_id=receipt.effect_id,
        receipt_id=receipt.receipt_id,
        safe_sink_commitment_sha256=receipt.safe_sink_commitment_sha256,
    )


def _safe_sink_match(
    expected: str,
    observed: PlatformReceiptRecord | None,
    match: PlatformReceiptRecord | None,
) -> AssertionObservation:
    selected = match or observed
    return AssertionObservation(
        AssertionStatus.PASSED if match is not None else AssertionStatus.FAILED,
        EvidenceSource.PLATFORM_SAFE_SINK,
        (
            EvidenceReason.ASSERTION_PASSED
            if match is not None
            else EvidenceReason.SAFE_SINK_COMMITMENT_MISMATCH
        ),
        session_id=selected.session_id if selected else None,
        effect_id=selected.effect_id if selected else None,
        receipt_id=selected.receipt_id if selected else None,
        safe_sink_commitment_sha256=(selected.safe_sink_commitment_sha256 if selected else None),
        expected_value_commitment_sha256=expected,
        observed_value_commitment_sha256=(
            selected.safe_sink_commitment_sha256 if selected is not None else None
        ),
    )


def _check_session_assertion(
    assertion: RequiredSessionReachedAssertion | RequiredToolSequenceObservedAssertion,
    snapshot: PlatformEvidenceSnapshot,
) -> AssertionObservation:
    if not snapshot.session_trace_available:
        return AssertionObservation(
            AssertionStatus.NOT_EVALUABLE,
            EvidenceSource.PLATFORM_SESSION_TRACE,
            EvidenceReason.SESSION_TRACE_UNAVAILABLE,
            session_id=assertion.session_id,
        )
    session = next(
        (item for item in snapshot.sessions if item.session_id == assertion.session_id),
        None,
    )
    if session is None or not session.reached:
        return AssertionObservation(
            AssertionStatus.FAILED,
            EvidenceSource.PLATFORM_SESSION_TRACE,
            EvidenceReason.SESSION_NOT_REACHED,
            session_id=assertion.session_id,
        )
    if isinstance(assertion, RequiredSessionReachedAssertion):
        matches = True
    else:
        matches = _is_subsequence(
            assertion.expected_tool_sequence,
            session.accepted_tool_sequence,
        )
    return AssertionObservation(
        AssertionStatus.PASSED if matches else AssertionStatus.FAILED,
        EvidenceSource.PLATFORM_SESSION_TRACE,
        EvidenceReason.ASSERTION_PASSED if matches else EvidenceReason.TOOL_SEQUENCE_MISMATCH,
        session_id=assertion.session_id,
    )


def _is_subsequence(expected: tuple[str, ...], observed: tuple[str, ...]) -> bool:
    iterator = iter(observed)
    return all(any(candidate == item for candidate in iterator) for item in expected)
