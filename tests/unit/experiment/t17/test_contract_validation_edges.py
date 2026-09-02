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
from skillflow.experiment.t17.metric_models import (
    T17IntervalEstimate,
    T17ProvenanceReport,
)
from skillflow.experiment.t17.scripted_models import ProvenanceAggregateSummary


def _domain(identifier: str = "domain") -> EvidenceDomain:
    return EvidenceDomain(
        domain_id=identifier,
        kind=EvidenceDomainKind.CONTRACT,
        protocol_id="protocol",
        simulation_only=True,
        external_effects_simulated=True,
    )


def test_evidence_domain_identity_and_single_domain_gate() -> None:
    domain = _domain()
    assert require_single_evidence_domain((domain, domain)) == domain
    with pytest.raises(EvidenceDomainMismatchError) as empty:
        require_single_evidence_domain(())
    assert str(empty.value).endswith(": ")
    with pytest.raises(EvidenceDomainMismatchError, match="left, right"):
        require_single_evidence_domain((_domain("left"), _domain("right")))
    with pytest.raises(ValidationError, match="同时存在"):
        EvidenceDomain(
            domain_id="partial",
            kind=EvidenceDomainKind.REFERENCE_HARNESS,
            protocol_id="protocol",
            simulation_only=False,
            external_effects_simulated=True,
            provider="openai",
        )


@pytest.mark.parametrize(
    "payload",
    [
        {
            "hook": HookName.AUTHORIZATION,
            "required": False,
            "available": False,
            "status": MeasurementStatus.NOT_APPLICABLE,
            "reason": "not required",
        },
        {
            "hook": HookName.AUTHORIZATION,
            "required": True,
            "available": False,
            "status": MeasurementStatus.NOT_AVAILABLE,
            "reason": "missing",
        },
        {
            "hook": HookName.AUTHORIZATION,
            "required": True,
            "available": True,
            "status": MeasurementStatus.INCOMPLETE,
            "reason": "partial",
        },
        {
            "hook": HookName.AUTHORIZATION,
            "required": True,
            "available": True,
            "status": MeasurementStatus.MEASURED,
        },
    ],
)
def test_hook_capability_valid_states(payload: dict[str, object]) -> None:
    assert HookCapability.model_validate(payload).status == payload["status"]


def test_hook_capability_rejects_status_and_reason_mismatch() -> None:
    with pytest.raises(ValidationError, match="status"):
        HookCapability(
            hook=HookName.AUTHORIZATION,
            required=True,
            available=False,
            status=MeasurementStatus.MEASURED,
        )
    with pytest.raises(ValidationError, match="reason"):
        HookCapability(
            hook=HookName.AUTHORIZATION,
            required=True,
            available=True,
            status=MeasurementStatus.INCOMPLETE,
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"status": "measured"},
        {"status": "measured", "numerator": 0, "denominator": 0, "value": 0},
        {"status": "measured", "numerator": 2, "denominator": 1, "value": 1},
        {
            "status": "measured",
            "numerator": 1,
            "denominator": 2,
            "scheduled_denominator": 3,
            "value": 0.5,
        },
        {"status": "measured", "numerator": 1, "denominator": 2, "value": 0.4},
        {"status": "incomplete", "reason": "partial"},
        {
            "status": "incomplete",
            "numerator": 2,
            "denominator": 2,
            "scheduled_denominator": 2,
            "reason": "partial",
        },
        {
            "status": "incomplete",
            "numerator": 1,
            "denominator": 2,
            "scheduled_denominator": 3,
            "value": 0.5,
        },
        {"status": "not_applicable", "numerator": 0, "reason": "none"},
        {"status": "not_available"},
    ],
)
def test_ratio_measurement_rejects_inconsistent_states(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError, match=r"比例|N/A|incomplete|measured|value"):
        RatioMeasurement.model_validate(payload)


def test_interval_validation_edges() -> None:
    invalid = [
        {
            "status": "measured",
            "method": "wilson_chain_descriptive",
        },
        {
            "status": "measured",
            "method": "wilson_chain_descriptive",
            "point": 0.5,
            "lower": 0.6,
            "upper": 0.7,
        },
        {
            "status": "measured",
            "method": "cluster_bootstrap",
            "point": 0.5,
            "lower": 0.4,
            "upper": 0.6,
            "resamples": 9,
            "seed": 1,
        },
        {
            "status": "measured",
            "method": "wilson_chain_descriptive",
            "point": 0.5,
            "lower": 0.4,
            "upper": 0.6,
            "resamples": 10_000,
        },
        {
            "status": "incomplete",
            "method": "cluster_bootstrap",
            "point": 0.5,
            "reason": "partial",
        },
        {
            "status": "incomplete",
            "method": "cluster_bootstrap",
        },
    ]
    for payload in invalid:
        with pytest.raises(ValidationError):
            T17IntervalEstimate.model_validate(payload)


def test_provenance_report_validation_edges() -> None:
    with pytest.raises(ValidationError):
        T17ProvenanceReport(
            status=MeasurementStatus.MEASURED,
            observed_runs=1,
            scheduled_runs=1,
            metrics=None,
        )
    metrics = ProvenanceAggregateSummary.model_construct()
    with pytest.raises(ValidationError):
        T17ProvenanceReport(
            status=MeasurementStatus.MEASURED,
            observed_runs=1,
            scheduled_runs=2,
            metrics=metrics,
        )
    with pytest.raises(ValidationError):
        T17ProvenanceReport(
            status=MeasurementStatus.INCOMPLETE,
            observed_runs=1,
            scheduled_runs=2,
            metrics=metrics,
        )
    report = T17ProvenanceReport(
        status=MeasurementStatus.MEASURED,
        observed_runs=2,
        scheduled_runs=2,
        metrics=metrics,
    )
    assert report.status is MeasurementStatus.MEASURED
