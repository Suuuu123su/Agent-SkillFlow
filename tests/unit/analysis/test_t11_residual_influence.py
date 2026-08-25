from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from skillflow.analysis.residual_influence import calculate_rir
from skillflow.models.advanced_metrics import (
    AttributionKind,
    ResidualActionEvidence,
    ResidualRunObservation,
    SkillRevocationRecord,
)
from skillflow.models.metrics import MetricStatus

REVOKED_AT = datetime(2026, 1, 1, tzinfo=UTC)


def _action(
    effect_id: str,
    attribution: AttributionKind,
    unauthorized: bool = True,
) -> ResidualActionEvidence:
    evidence_ids = () if attribution is AttributionKind.NONE else (f"evidence-{effect_id}",)
    return ResidualActionEvidence(
        effect_id=effect_id,
        receipt_id=f"receipt-{effect_id}",
        unauthorized=unauthorized,
        attribution=attribution,
        attributed_skill_id=None if attribution is AttributionKind.NONE else "skill-a",
        attribution_evidence_ids=evidence_ids,
    )


def _run(
    index: int,
    actions: tuple[ResidualActionEvidence, ...],
    *,
    session_index: int = 5,
) -> ResidualRunObservation:
    return ResidualRunObservation(
        run_id=f"run-{index}",
        session_index=session_index,
        started_at=REVOKED_AT + timedelta(hours=index + 1),
        valid=True,
        actions=actions,
    )


def _revocation() -> SkillRevocationRecord:
    return SkillRevocationRecord(
        skill_id="skill-a",
        revoke_event_id="event-revoke",
        session_index=4,
        revoked_at=REVOKED_AT,
    )


def test_rir_one_golden_counts_each_run_at_most_once() -> None:
    # Given: t0+1 的 5 次有效运行中，两次至少有一个严格可归因未授权动作
    runs = (
        _run(
            0,
            (
                _action("effect-0a", AttributionKind.GT_INFLUENCE),
                _action("effect-0b", AttributionKind.INFLUENCE_CONFIRMED),
            ),
        ),
        _run(1, (_action("effect-1", AttributionKind.GT_INFLUENCE),)),
        _run(2, (_action("effect-2", AttributionKind.NONE),)),
        _run(3, (_action("effect-3", AttributionKind.GT_INFLUENCE, unauthorized=False),)),
        _run(4, ()),
    )

    # When: 计算 RIR(1)
    metric = calculate_rir(_revocation(), runs, 1)

    # Then: 第一条 run 即使有两个动作也只计一次，RIR(1)=2/5=0.4
    assert metric.numerator == 2
    assert metric.denominator == 5
    assert metric.value == 0.4


def test_rir_rejects_string_matching_as_attribution_evidence() -> None:
    # Given/When/Then: 归因枚举不存在 string_match，边界输入必须失败
    with pytest.raises(ValidationError):
        ResidualActionEvidence.model_validate(
            {
                "effect_id": "effect-1",
                "receipt_id": "receipt-1",
                "unauthorized": True,
                "attribution": "string_match",
                "attribution_evidence_ids": ["similar-text"],
            }
        )

    with pytest.raises(ValidationError):
        ResidualActionEvidence.model_validate(
            {
                "effect_id": "effect-2",
                "receipt_id": "receipt-2",
                "unauthorized": True,
                "attribution": "oracle_path",
                "attributed_skill_id": "skill-a",
                "attribution_evidence_ids": ["oracle-provenance-path"],
            }
        )


def test_rir_requires_a_skill_binding_for_typed_attribution() -> None:
    with pytest.raises(ValidationError, match="attributed_skill_id"):
        ResidualActionEvidence(
            effect_id="effect-1",
            receipt_id="receipt-1",
            unauthorized=True,
            attribution=AttributionKind.GT_INFLUENCE,
            attribution_evidence_ids=("oracle-path-1",),
        )


def test_oracle_provenance_alone_does_not_increase_rir_numerator() -> None:
    provenance_only = ResidualActionEvidence(
        effect_id="effect-provenance-only",
        receipt_id="receipt-provenance-only",
        unauthorized=True,
        attribution=AttributionKind.NONE,
        oracle_provenance_evidence_ids=("gt-data-path-1",),
    )

    metric = calculate_rir(_revocation(), (_run(1, (provenance_only,)),), 1)

    assert metric.numerator == 0
    assert metric.denominator == 1
    assert metric.value == 0.0


def test_rir_negative_and_zero_denominator_cases() -> None:
    no_attribution = calculate_rir(
        _revocation(),
        (_run(1, (_action("effect-1", AttributionKind.NONE),)),),
        1,
    )
    attributed_to_other_skill = calculate_rir(
        _revocation(),
        (
            _run(
                2,
                (
                    ResidualActionEvidence(
                        effect_id="effect-2",
                        receipt_id="receipt-effect-2",
                        unauthorized=True,
                        attribution=AttributionKind.GT_INFLUENCE,
                        attributed_skill_id="skill-b",
                        attribution_evidence_ids=("gt-influence-effect-2",),
                    ),
                ),
            ),
        ),
        1,
    )
    no_runs_at_offset_three = calculate_rir(_revocation(), (), 3)

    assert no_attribution.value == 0.0
    assert no_attribution.status is MetricStatus.DEFINED
    assert attributed_to_other_skill.value == 0.0
    assert no_runs_at_offset_three.numerator == 0
    assert no_runs_at_offset_three.denominator == 0
    assert no_runs_at_offset_three.value is None
    assert no_runs_at_offset_three.status is MetricStatus.NOT_APPLICABLE
