import pytest
from pydantic import ValidationError

from skillflow.experiment.t17.contracts import (
    EvidenceDomain,
    EvidenceDomainKind,
    EvidenceDomainMismatchError,
    HookCapability,
    HookName,
    MeasurementStatus,
    RatioMeasurement,
    require_single_evidence_domain,
)


def _domain(identifier: str) -> EvidenceDomain:
    return EvidenceDomain(
        domain_id=identifier,
        kind=EvidenceDomainKind.REFERENCE_HARNESS,
        protocol_id="t17-reference-v1",
        simulation_only=False,
        external_effects_simulated=True,
        provider="openai",
        model_id="gpt-5.6-luna",
        model_revision="gpt-5.6-luna",
    )


def test_ratio_measurement_accepts_measured_zero_when_denominator_exists() -> None:
    # Given: a measured ratio with a real denominator and zero numerator.
    # When: the T17 ratio boundary parses it.
    result = RatioMeasurement(
        status=MeasurementStatus.MEASURED,
        numerator=0,
        denominator=4,
        scheduled_denominator=4,
        value=0.0,
    )

    # Then: zero remains a measured value rather than N/A.
    assert result.value == 0.0


def test_ratio_measurement_rejects_not_available_disguised_as_zero() -> None:
    # Given: a missing Hook represented with a fabricated numeric zero.
    # When/Then: the strict boundary rejects it.
    with pytest.raises(ValidationError):
        RatioMeasurement(
            status=MeasurementStatus.NOT_AVAILABLE,
            numerator=0,
            denominator=4,
            scheduled_denominator=4,
            value=0.0,
            reason="authorization Hook 缺失",
        )


def test_ratio_measurement_preserves_partial_counts_without_reporting_value() -> None:
    # Given: two observed Trials from four scheduled Trials.
    # When: an incomplete metric is constructed.
    result = RatioMeasurement(
        status=MeasurementStatus.INCOMPLETE,
        numerator=1,
        denominator=2,
        scheduled_denominator=4,
        value=None,
        reason="阶段只完成一半",
    )

    # Then: partial counts remain inspectable but no biased ratio is published.
    assert (result.numerator, result.denominator, result.value) == (1, 2, None)


def test_hook_capability_distinguishes_unavailable_from_not_applicable() -> None:
    # Given: one required missing Hook and one out-of-scope Hook.
    # When: both capability records are parsed.
    missing = HookCapability(
        hook=HookName.AUTHORIZATION,
        required=True,
        available=False,
        status=MeasurementStatus.NOT_AVAILABLE,
        reason="平台未提供 Grant Hook",
    )
    irrelevant = HookCapability(
        hook=HookName.REVOCATION,
        required=False,
        available=False,
        status=MeasurementStatus.NOT_APPLICABLE,
        reason="该场景没有撤销",
    )

    # Then: their machine-readable statuses remain distinct.
    assert missing.status is MeasurementStatus.NOT_AVAILABLE
    assert irrelevant.status is MeasurementStatus.NOT_APPLICABLE


def test_evidence_domains_cannot_be_micro_aggregated_when_they_differ() -> None:
    # Given: two otherwise valid but distinct evidence domains.
    # When/Then: the aggregation guard rejects pooling them.
    with pytest.raises(EvidenceDomainMismatchError):
        require_single_evidence_domain((_domain("model1"), _domain("model2")))
