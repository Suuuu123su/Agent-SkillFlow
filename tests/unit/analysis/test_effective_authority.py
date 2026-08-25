from dataclasses import replace

import pytest

from skillflow.analysis.effective_authority import calculate_uea
from skillflow.analysis.errors import AnalysisInvariantError
from skillflow.analysis.facts import EffectMetricSample
from skillflow.graph.models import BoundaryDepth
from skillflow.models.effects import CapabilityEffect
from skillflow.models.enums import CapabilityAction, Lifetime, Scope
from skillflow.models.metrics import EffectPathEvidence
from skillflow.models.resources import ResourceRef
from skillflow.policy.reasons import PolicyReasonCode


def effect_sample(
    suffix: str,
    *,
    authorized: bool,
) -> EffectMetricSample:
    return EffectMetricSample(
        effect_id=f"effect-{suffix}",
        receipt_id=f"receipt-{suffix}",
        decision_id=f"decision-{suffix}",
        effect=CapabilityEffect(
            source=ResourceRef("context:/task//payload"),
            action=CapabilityAction.NETWORK_SEND,
            sink=ResourceRef("mock://external"),
            scope=Scope.EXACT_SINK,
            lifetime=Lifetime.CALL,
            sensitivity=4,
        ),
        executed=True,
        authorized=authorized,
        manifest_declared=True,
        matched_grant_ids=(),
        paths=(
            EffectPathEvidence(
                node_ids=("principal:skill", f"effect:effect-{suffix}"),
                evidence_event_ids=(f"event-{suffix}",),
                boundary_depth=BoundaryDepth(
                    context=0,
                    memory=0,
                    session=0,
                    skill=1,
                    tool=0,
                    total=1,
                ),
            ),
        ),
    )


def test_uea_golden_counts_instances_and_deduplicates_canonical_types() -> None:
    # Given: 三个已执行 Effect 中两个无有效授权，且二者规范化类型相同
    samples = (
        effect_sample("authorized", authorized=True),
        effect_sample("grant-missing", authorized=False),
        replace(
            effect_sample("manifest-missing", authorized=False),
            manifest_declared=False,
            matched_grant_ids=("grant-2",),
        ),
    )

    # When: 计算 UEA
    result = calculate_uea(samples)

    # Then: 实例数为 2、类型数为 1、主权重逐实例累加
    assert result.summary.uea_count == 2
    assert result.summary.uea_type_count == 1
    assert result.summary.uea_weight == 2.0
    assert result.unauthorized_effects[0].reason_codes == (PolicyReasonCode.USER_GRANT_MISSING,)
    assert result.unauthorized_effects[1].reason_codes == (
        PolicyReasonCode.MANIFEST_PERMISSION_MISSING,
    )


def test_uea_duplicate_projection_does_not_double_count_same_receipt() -> None:
    # Given: 同一 Effect/Receipt 结构化记录被重复投影
    sample = effect_sample("duplicate", authorized=False)

    # When: 输入两个相同实例
    result = calculate_uea((sample, sample))

    # Then: 仍只计一个实际实例
    assert result.summary.uea_count == 1
    assert result.summary.uea_type_count == 1


def test_uea_empty_or_unexecuted_inputs_return_zero_with_no_evidence() -> None:
    # Given: 一个未执行请求和一个空输入
    unexecuted = replace(effect_sample("blocked", authorized=False), executed=False)

    # When: 分别计算两组 UEA
    blocked = calculate_uea((unexecuted,))
    empty = calculate_uea(())

    # Then: 没有 Receipt 实例进入 UEA 分子
    assert blocked.summary.uea_count == 0
    assert empty.summary.uea_count == 0
    assert empty.summary.evidence_ids == ()


def test_uea_rejects_unauthorized_instance_without_path_evidence() -> None:
    sample = replace(
        effect_sample("missing-path", authorized=False),
        paths=(),
    )

    with pytest.raises(AnalysisInvariantError) as captured:
        calculate_uea((sample,))

    assert captured.value.operation == "calculate_uea"
