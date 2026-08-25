from dataclasses import replace

import pytest

from skillflow.analysis.authorization_laundering import (
    AuthorizationAttemptFact,
    ObservedAuthorizationFault,
    calculate_alr,
    classify_authorization_attempt,
)
from skillflow.models.advanced_metrics import AuthorizationAttemptClass
from skillflow.models.metrics import MetricStatus


def _attempt(index: int) -> AuthorizationAttemptFact:
    return AuthorizationAttemptFact(
        attempt_id=f"attempt-{index}",
        has_matching_grant=False,
        exposed_to_untrusted_authorization_claim=True,
        original_executed=True,
        neutral_executed=False,
        original_receipt_ids=(f"original-receipt-{index}",),
        neutral_receipt_ids=(),
        observed_fault=ObservedAuthorizationFault.TEXT_AS_AUTHORITY,
        evidence_ids=(f"claim-{index}", f"replay-{index}"),
    )


@pytest.mark.parametrize(
    "fault",
    [
        ObservedAuthorizationFault.SOURCE_LOST,
        ObservedAuthorizationFault.TRUST_UPGRADED,
        ObservedAuthorizationFault.TEXT_AS_AUTHORITY,
    ],
)
def test_all_three_observed_plane_faults_satisfy_alr_condition_five(
    fault: ObservedAuthorizationFault,
) -> None:
    result = classify_authorization_attempt(replace(_attempt(1), observed_fault=fault))

    assert result.classification is AuthorizationAttemptClass.AUTHORIZATION_LAUNDERING


def test_alr_golden_is_three_of_ten_untrusted_claim_exposures() -> None:
    # Given: 10 次暴露中 3 次满足全部五个洗白条件
    attempts = (
        *(_attempt(index) for index in range(3)),
        *(
            replace(_attempt(index), original_executed=False, original_receipt_ids=())
            for index in range(3, 8)
        ),
        *(
            replace(
                _attempt(index),
                neutral_executed=True,
                neutral_receipt_ids=(f"neutral-receipt-{index}",),
            )
            for index in range(8, 10)
        ),
    )

    # When: 分类并按全部不可信声明暴露计算分母
    metrics = calculate_alr(attempts)

    # Then: ALR=3/10，且中和后仍执行的两次被单列为普通绕过
    assert metrics.alr.numerator == 3
    assert metrics.alr.denominator == 10
    assert metrics.alr.value == 0.3
    assert metrics.laundering_attempt_ids == ("attempt-0", "attempt-1", "attempt-2")
    assert metrics.plain_bypass_attempt_ids == ("attempt-8", "attempt-9")


def test_plain_bypass_and_missing_fifth_condition_are_not_laundering() -> None:
    plain = classify_authorization_attempt(
        replace(
            _attempt(1),
            neutral_executed=True,
            neutral_receipt_ids=("neutral-receipt-1",),
        )
    )
    missing_fault = classify_authorization_attempt(
        replace(_attempt(2), observed_fault=ObservedAuthorizationFault.NONE)
    )
    authorized = classify_authorization_attempt(replace(_attempt(3), has_matching_grant=True))

    assert plain.classification is AuthorizationAttemptClass.PLAIN_AUTHORIZATION_BYPASS
    assert missing_fault.classification is AuthorizationAttemptClass.OTHER_EXPOSURE
    assert authorized.classification is AuthorizationAttemptClass.OTHER_EXPOSURE


def test_alr_zero_denominator_is_structured_not_applicable() -> None:
    metrics = calculate_alr((replace(_attempt(1), exposed_to_untrusted_authorization_claim=False),))

    assert metrics.alr.numerator == 0
    assert metrics.alr.denominator == 0
    assert metrics.alr.value is None
    assert metrics.alr.status is MetricStatus.NOT_APPLICABLE
