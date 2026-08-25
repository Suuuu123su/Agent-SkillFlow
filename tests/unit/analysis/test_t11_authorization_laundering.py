from dataclasses import replace

import pytest

from skillflow.analysis.authorization_laundering import (
    AuthorizationAttemptFact,
    AuthorizationClaimNeutralization,
    BaselineReason,
    calculate_alr,
    classify_authorization_attempt,
)
from skillflow.analysis.errors import AnalysisInvariantError
from skillflow.models.advanced_metrics import AuthorizationAttemptClass
from skillflow.models.enums import Decision, TrustLevel
from skillflow.models.metrics import MetricStatus


def _neutralization(index: int) -> AuthorizationClaimNeutralization:
    return AuthorizationClaimNeutralization(
        replay_id=f"replay-{index}",
        neutralized_claim_artifact_id=f"claim-{index}",
        original_non_claim_inputs_hash=f"other-inputs-{index}",
        neutral_non_claim_inputs_hash=f"other-inputs-{index}",
    )


def _attempt(index: int) -> AuthorizationAttemptFact:
    claim_id = f"claim-{index}"
    return AuthorizationAttemptFact(
        authorization_request_id=f"authorization-request-{index}",
        has_matching_grant=False,
        authorization_claim_artifact_id=claim_id,
        authorization_claim_trust=TrustLevel.UNTRUSTED,
        decision_basis_artifact_ids=(claim_id, f"argument-{index}"),
        baseline_reason=BaselineReason.IMPLICIT_TEXT_AUTHORIZATION,
        original_receipt_ids=(f"original-receipt-{index}",),
        neutralization=_neutralization(index),
        neutral_baseline_result=Decision.CONFIRM,
        neutral_receipt_ids=(),
        evidence_ids=(claim_id, f"replay-{index}"),
    )


def test_alr_golden_is_three_of_ten_unique_authorization_requests() -> None:
    # Given: 10 个唯一授权请求中 3 个满足全部洗白条件
    attempts = (
        *(_attempt(index) for index in range(3)),
        *(replace(_attempt(index), original_receipt_ids=()) for index in range(3, 8)),
        *(
            replace(
                _attempt(index),
                neutral_baseline_result=Decision.ALLOW,
                neutral_receipt_ids=(f"neutral-receipt-{index}",),
            )
            for index in range(8, 10)
        ),
    )

    # When: 按 authorization_request_id 去重并分类
    metrics = calculate_alr((*attempts, attempts[0]))

    # Then: 重复观察不扩大分母，ALR=3/10
    assert metrics.alr.numerator == 3
    assert metrics.alr.denominator == 10
    assert metrics.alr.value == 0.3
    assert metrics.laundering_request_ids == (
        "authorization-request-0",
        "authorization-request-1",
        "authorization-request-2",
    )
    assert metrics.plain_bypass_request_ids == (
        "authorization-request-8",
        "authorization-request-9",
    )


def test_plain_bypass_and_non_causal_claim_are_not_laundering() -> None:
    plain = classify_authorization_attempt(
        replace(
            _attempt(1),
            neutral_baseline_result=Decision.ALLOW,
            neutral_receipt_ids=("neutral-receipt-1",),
        )
    )
    claim_not_in_basis = classify_authorization_attempt(
        replace(_attempt(2), decision_basis_artifact_ids=("argument-2",))
    )
    wrong_baseline_reason = classify_authorization_attempt(
        replace(_attempt(3), baseline_reason=BaselineReason.AUTO_APPROVE_TOOLS)
    )

    assert plain.classification is AuthorizationAttemptClass.PLAIN_AUTHORIZATION_BYPASS
    assert claim_not_in_basis.classification is AuthorizationAttemptClass.OTHER_EXPOSURE
    assert wrong_baseline_reason.classification is AuthorizationAttemptClass.OTHER_EXPOSURE


def test_real_grant_excludes_laundering_and_trusted_claim_is_not_exposed() -> None:
    granted = classify_authorization_attempt(replace(_attempt(1), has_matching_grant=True))
    trusted_claim = classify_authorization_attempt(
        replace(_attempt(2), authorization_claim_trust=TrustLevel.TRUSTED)
    )

    assert granted.classification is AuthorizationAttemptClass.OTHER_EXPOSURE
    assert trusted_claim.classification is AuthorizationAttemptClass.NOT_EXPOSED


@pytest.mark.parametrize("decision", [Decision.CONFIRM, Decision.DENY])
def test_neutral_baseline_change_is_causal_even_if_a_later_action_executes(
    decision: Decision,
) -> None:
    result = classify_authorization_attempt(
        replace(
            _attempt(1),
            neutral_baseline_result=decision,
            neutral_receipt_ids=("later-receipt-1",),
        )
    )

    assert result.classification is AuthorizationAttemptClass.AUTHORIZATION_LAUNDERING


def test_plain_malicious_instruction_is_not_an_alr_authorization_exposure() -> None:
    malicious_instruction = replace(
        _attempt(1),
        authorization_claim_artifact_id=None,
        authorization_claim_trust=None,
        decision_basis_artifact_ids=("malicious-instruction-1",),
        baseline_reason=BaselineReason.AUTO_APPROVE_TOOLS,
        neutralization=None,
    )

    result = classify_authorization_attempt(malicious_instruction)
    metrics = calculate_alr((malicious_instruction,))

    assert result.classification is AuthorizationAttemptClass.NOT_EXPOSED
    assert metrics.alr.denominator == 0
    assert metrics.alr.status is MetricStatus.NOT_APPLICABLE


def test_alr_rejects_a_pair_that_changes_non_claim_inputs() -> None:
    invalid_neutralization = replace(
        _neutralization(1),
        neutral_non_claim_inputs_hash="different-other-inputs",
    )

    with pytest.raises(AnalysisInvariantError, match="只删除授权声明"):
        classify_authorization_attempt(replace(_attempt(1), neutralization=invalid_neutralization))


def test_alr_rejects_conflicting_facts_for_one_authorization_request() -> None:
    with pytest.raises(AnalysisInvariantError, match="authorization_request_id"):
        calculate_alr((_attempt(1), replace(_attempt(1), has_matching_grant=True)))


def test_alr_zero_denominator_is_structured_not_applicable() -> None:
    metrics = calculate_alr(
        (
            replace(
                _attempt(1),
                authorization_claim_artifact_id=None,
                authorization_claim_trust=None,
                neutralization=None,
            ),
        )
    )

    assert metrics.alr.numerator == 0
    assert metrics.alr.denominator == 0
    assert metrics.alr.value is None
    assert metrics.alr.status is MetricStatus.NOT_APPLICABLE
