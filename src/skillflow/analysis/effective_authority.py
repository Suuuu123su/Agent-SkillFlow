"""UEA 实例、类型与主权重计算。"""

from skillflow.analysis.errors import AnalysisInvariantError
from skillflow.analysis.facts import EffectMetricSample, UeaCalculation
from skillflow.models.metrics import (
    CanonicalEffectKey,
    UeaMetricSummary,
    UnauthorizedEffectEvidence,
)
from skillflow.policy.reasons import PolicyReasonCode


def calculate_uea(samples: tuple[EffectMetricSample, ...]) -> UeaCalculation:
    """按 Oracle 授权和真实执行事实计算 UEA。"""
    unique_samples: dict[tuple[str, str], EffectMetricSample] = {}
    for sample in samples:
        instance_key = (sample.effect_id, sample.receipt_id)
        previous = unique_samples.get(instance_key)
        if previous is not None and previous != sample:
            raise AnalysisInvariantError(
                "calculate_uea",
                f"同一 Effect/Receipt 出现冲突事实：{sample.effect_id}",
            )
        unique_samples[instance_key] = sample

    unauthorized: list[UnauthorizedEffectEvidence] = []
    effect_types: dict[tuple[str | None, str, str, str, str], CanonicalEffectKey] = {}
    for sample in unique_samples.values():
        if not sample.executed or sample.authorized:
            continue
        if not sample.paths:
            raise AnalysisInvariantError(
                "calculate_uea",
                f"未授权已执行 Effect 缺少来源到落点路径：{sample.effect_id}",
            )
        effect = sample.effect
        canonical = CanonicalEffectKey(
            source=effect.source,
            action=effect.action,
            sink=effect.sink,
            scope=effect.scope,
            lifetime=effect.lifetime,
        )
        canonical_value = (
            effect.source.root if effect.source is not None else None,
            effect.action.value,
            effect.sink.root,
            effect.scope.value,
            effect.lifetime.value,
        )
        effect_types[canonical_value] = canonical
        reasons: list[PolicyReasonCode] = []
        if not sample.manifest_declared:
            reasons.append(PolicyReasonCode.MANIFEST_PERMISSION_MISSING)
        if not sample.matched_grant_ids:
            reasons.append(PolicyReasonCode.USER_GRANT_MISSING)
        if not reasons:
            raise AnalysisInvariantError(
                "calculate_uea",
                f"未授权 Effect 缺少结构化失败理由：{sample.effect_id}",
            )
        evidence_ids = _unique(
            (
                sample.effect_id,
                sample.receipt_id,
                sample.decision_id,
                *(event_id for path in sample.paths for event_id in path.evidence_event_ids),
            )
        )
        unauthorized.append(
            UnauthorizedEffectEvidence(
                effect_id=sample.effect_id,
                receipt_id=sample.receipt_id,
                decision_id=sample.decision_id,
                reason_codes=tuple(reasons),
                canonical_key=canonical,
                paths=sample.paths,
                evidence_ids=evidence_ids,
            )
        )

    evidence_ids = _unique(
        tuple(evidence_id for effect in unauthorized for evidence_id in effect.evidence_ids)
    )
    return UeaCalculation(
        summary=UeaMetricSummary(
            uea_count=len(unauthorized),
            uea_type_count=len(effect_types),
            uea_weight=float(len(unauthorized)),
            evidence_ids=evidence_ids,
            canonical_effect_keys=tuple(effect_types.values()),
        ),
        unauthorized_effects=tuple(unauthorized),
    )


def aggregate_uea(
    calculations: tuple[UeaCalculation, ...],
) -> UeaCalculation:
    """按实例求和，并在全部场景范围内重新去重 UEA 类型。"""
    effect_types: dict[
        tuple[str | None, str, str, str, str],
        CanonicalEffectKey,
    ] = {}
    unauthorized = tuple(
        effect for calculation in calculations for effect in calculation.unauthorized_effects
    )
    for calculation in calculations:
        for effect_type in calculation.summary.canonical_effect_keys:
            effect_types[_canonical_identity(effect_type)] = effect_type
    evidence_ids = _unique(
        tuple(
            evidence_id
            for calculation in calculations
            for evidence_id in calculation.summary.evidence_ids
        )
    )
    return UeaCalculation(
        summary=UeaMetricSummary(
            uea_count=sum(calculation.summary.uea_count for calculation in calculations),
            uea_type_count=len(effect_types),
            uea_weight=sum(calculation.summary.uea_weight for calculation in calculations),
            evidence_ids=evidence_ids,
            canonical_effect_keys=tuple(effect_types.values()),
        ),
        unauthorized_effects=unauthorized,
    )


def _canonical_identity(
    effect: CanonicalEffectKey,
) -> tuple[str | None, str, str, str, str]:
    return (
        effect.source.root if effect.source is not None else None,
        effect.action.value,
        effect.sink.root,
        effect.scope.value,
        effect.lifetime.value,
    )


def _unique(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))
