from skillflow.models.enums import CapabilityAction
from skillflow.models.metrics import MetricStatus, RatioMetric
from skillflow.pilot.comparison import compare_observations
from skillflow.pilot.models import (
    PilotAdapterKind,
    PilotEffectEvidence,
    PilotObservation,
    ProvenanceBasis,
)


def _observation(
    adapter: PilotAdapterKind,
    *,
    receipt: str,
    provenance: RatioMetric,
    policy_fact: str,
    provenance_basis: ProvenanceBasis,
) -> PilotObservation:
    return PilotObservation(
        adapter=adapter,
        scenario_id="G0",
        security_events=(),
        target_effects=(
            PilotEffectEvidence(
                effect_alias="memory-send",
                action=CapabilityAction.NETWORK_SEND,
                receipt_id=receipt,
                origin_ids=("asset:memory-payload",),
                policy_fact=policy_fact,
            ),
        ),
        provenance_recall=provenance,
        provenance_basis=provenance_basis,
        missing_hooks=(
            ()
            if adapter is PilotAdapterKind.MOCK
            else ("grant_matcher", "artifact_provenance_graph")
        ),
    )


def test_comparison_keeps_matching_effects_and_exposes_policy_gap() -> None:
    full = RatioMetric(
        numerator=1,
        denominator=1,
        value=1.0,
        status=MetricStatus.DEFINED,
        evidence_ids=("effect-1",),
    )
    mock = _observation(
        PilotAdapterKind.MOCK,
        receipt="mock-receipt",
        provenance=full,
        policy_fact="authorized_allow",
        provenance_basis=ProvenanceBasis.GRAPH_WIDE_ARTIFACTS,
    )
    openclaw = _observation(
        PilotAdapterKind.OPENCLAW,
        receipt="openclaw-receipt",
        provenance=full,
        policy_fact="platform_executed_no_grant_fact",
        provenance_basis=ProvenanceBasis.TARGET_EFFECT_LABELS,
    )

    comparison = compare_observations(mock, openclaw)

    assert comparison.effect_count_match is True
    assert comparison.mock_effect_count == comparison.openclaw_effect_count == 1
    assert comparison.provenance_delta is None
    assert comparison.provenance_basis_match is False
    assert comparison.policy_match is False
    assert comparison.differences == ("grant_matcher", "artifact_provenance_graph")


def test_comparison_preserves_na_instead_of_turning_it_into_zero() -> None:
    missing = RatioMetric(
        numerator=0,
        denominator=0,
        value=None,
        status=MetricStatus.NOT_APPLICABLE,
    )
    mock = _observation(
        PilotAdapterKind.MOCK,
        receipt="mock-receipt",
        provenance=missing,
        policy_fact="authorized_allow",
        provenance_basis=ProvenanceBasis.GRAPH_WIDE_ARTIFACTS,
    )
    openclaw = _observation(
        PilotAdapterKind.OPENCLAW,
        receipt="openclaw-receipt",
        provenance=missing,
        policy_fact="authorized_allow",
        provenance_basis=ProvenanceBasis.GRAPH_WIDE_ARTIFACTS,
    )

    comparison = compare_observations(mock, openclaw)

    assert comparison.provenance_delta is None
