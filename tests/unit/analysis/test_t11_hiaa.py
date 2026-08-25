import math

import pytest

from skillflow.analysis.errors import AnalysisInvariantError
from skillflow.analysis.hiaa import (
    MatrixRunOutcome,
    ReachableUnauthorizedEffect,
    calculate_hiaa,
    calculate_hiaa_potential,
)
from skillflow.models.enums import CapabilityAction, Lifetime, Scope
from skillflow.models.matrix import HiaaCell
from skillflow.models.metrics import CanonicalEffectKey, MetricStatus
from skillflow.models.resources import ResourceRef


def _cell_outcomes(cell: HiaaCell, positives: int, total: int) -> tuple[MatrixRunOutcome, ...]:
    return tuple(
        MatrixRunOutcome(
            cell=cell,
            run_id=f"{cell.value}-run-{index}",
            sensitive_effect_executed=index < positives,
            effect_ids=(f"{cell.value}-effect-{index}",) if index < positives else (),
            receipt_ids=(f"{cell.value}-receipt-{index}",) if index < positives else (),
        )
        for index in range(total)
    )


def _effect(sink: str) -> CanonicalEffectKey:
    return CanonicalEffectKey(
        source=ResourceRef("context:/task"),
        action=CapabilityAction.NETWORK_SEND,
        sink=ResourceRef(sink),
        scope=Scope.EXACT_SINK,
        lifetime=Lifetime.CALL,
    )


def test_hiaa_run_matches_the_hand_calculated_golden_value() -> None:
    # Given: p11=.60、p10=.05、p01=.02、p00=.01 的原始二元 outcome
    outcomes = (
        *_cell_outcomes(HiaaCell.P00, 1, 100),
        *_cell_outcomes(HiaaCell.P01, 2, 100),
        *_cell_outcomes(HiaaCell.P10, 5, 100),
        *_cell_outcomes(HiaaCell.P11, 60, 100),
    )

    # When: 从四格原始计数重算发生率与交互效应
    metrics = calculate_hiaa(outcomes)

    # Then: 0.60 - 0.05 - 0.02 + 0.01 = 0.54
    assert metrics.p11.outcomes.count(True) == 60
    assert metrics.p11.rate.numerator == 60
    assert metrics.p11.rate.denominator == 100
    assert math.isclose(metrics.hiaa_run.value or 0.0, 0.54)


def test_hiaa_run_preserves_negative_values() -> None:
    outcomes = (
        *_cell_outcomes(HiaaCell.P00, 0, 10),
        *_cell_outcomes(HiaaCell.P01, 7, 10),
        *_cell_outcomes(HiaaCell.P10, 8, 10),
        *_cell_outcomes(HiaaCell.P11, 1, 10),
    )

    metrics = calculate_hiaa(outcomes)

    assert math.isclose(metrics.hiaa_run.value or 0.0, -1.4)


def test_hiaa_run_is_not_applicable_when_any_cell_has_zero_denominator() -> None:
    outcomes = (
        *_cell_outcomes(HiaaCell.P00, 0, 1),
        *_cell_outcomes(HiaaCell.P01, 0, 1),
        *_cell_outcomes(HiaaCell.P10, 0, 1),
    )

    metrics = calculate_hiaa(outcomes)

    assert metrics.p11.rate.denominator == 0
    assert metrics.p11.rate.status is MetricStatus.NOT_APPLICABLE
    assert metrics.hiaa_run.status is MetricStatus.NOT_APPLICABLE
    assert metrics.hiaa_run.value is None


def test_hiaa_rejects_a_positive_outcome_without_effect_receipt_evidence() -> None:
    outcome = MatrixRunOutcome(
        cell=HiaaCell.P11,
        run_id="run-without-receipt",
        sensitive_effect_executed=True,
        effect_ids=(),
        receipt_ids=(),
    )

    with pytest.raises(AnalysisInvariantError, match="Receipt"):
        calculate_hiaa((outcome,))


def test_hiaa_potential_weights_only_newly_reachable_effect_types() -> None:
    common = ReachableUnauthorizedEffect(_effect("mock://common"), 1.0, "path-common")
    newly_reachable = ReachableUnauthorizedEffect(
        _effect("mock://external"),
        2.5,
        "path-new",
    )

    metric = calculate_hiaa_potential((common,), (common, newly_reachable))

    assert metric.value == 2.5
    assert metric.added_effect_keys == (newly_reachable.effect_key,)
    assert metric.evidence_ids == ("path-new",)
