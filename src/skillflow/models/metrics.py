"""T09 风险指标、比例状态与证据链数据契约。"""

import math
from enum import StrEnum, unique
from typing import Annotated, Self, assert_never

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from skillflow.graph.models import BoundaryDepth
from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.enums import CapabilityAction, Lifetime, Scope
from skillflow.models.resources import ResourceRef
from skillflow.policy.reasons import PolicyReasonCode

NonNegativeInt = Annotated[int, Field(ge=0)]
NonNegativeFloat = Annotated[float, Field(ge=0.0)]
UnitInterval = Annotated[float, Field(ge=0.0, le=1.0)]
SignedUnitInterval = Annotated[float, Field(ge=-1.0, le=1.0)]


@unique
class MetricStatus(StrEnum):
    """比例指标是否有可解释分母。"""

    DEFINED = "defined"
    NOT_APPLICABLE = "not_applicable"


class RatioMetric(StrictModel):
    """值域为零到一的比例及其原始计数和证据。"""

    numerator: NonNegativeInt
    denominator: NonNegativeInt
    value: UnitInterval | None
    status: MetricStatus
    evidence_ids: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def require_consistent_ratio(self) -> Self:
        """拒绝把零分母伪装成零或把定义值标成 N/A。"""
        match self.status:
            case MetricStatus.DEFINED:
                if self.denominator == 0 or self.value is None:
                    raise PydanticCustomError(
                        "defined_ratio_missing_value",
                        "defined 比例要求非零 denominator 和 value",
                    )
                expected = self.numerator / self.denominator
                if not math.isclose(self.value, expected, rel_tol=1e-12, abs_tol=1e-12):
                    raise PydanticCustomError(
                        "defined_ratio_value_mismatch",
                        "value 必须等于 numerator / denominator",
                    )
            case MetricStatus.NOT_APPLICABLE:
                if self.numerator != 0 or self.denominator != 0 or self.value is not None:
                    raise PydanticCustomError(
                        "not_applicable_ratio_has_value",
                        "not_applicable 比例必须是 0/0 且 value 为 null",
                    )
            case _ as unreachable:
                assert_never(unreachable)
        return self


class SignedRatioMetric(StrictModel):
    """允许为负的比例差及其精确整数分子、分母。"""

    numerator: int
    denominator: NonNegativeInt
    value: SignedUnitInterval | None
    status: MetricStatus
    evidence_ids: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def require_consistent_ratio(self) -> Self:
        """对 Decay 执行与普通比例相同的零分母纪律。"""
        match self.status:
            case MetricStatus.DEFINED:
                if self.denominator == 0 or self.value is None:
                    raise PydanticCustomError(
                        "defined_signed_ratio_missing_value",
                        "defined 比例差要求非零 denominator 和 value",
                    )
                expected = self.numerator / self.denominator
                if not math.isclose(self.value, expected, rel_tol=1e-12, abs_tol=1e-12):
                    raise PydanticCustomError(
                        "defined_signed_ratio_value_mismatch",
                        "value 必须等于 numerator / denominator",
                    )
            case MetricStatus.NOT_APPLICABLE:
                if self.numerator != 0 or self.denominator != 0 or self.value is not None:
                    raise PydanticCustomError(
                        "not_applicable_signed_ratio_has_value",
                        "not_applicable 比例差必须是 0/0 且 value 为 null",
                    )
            case _ as unreachable:
                assert_never(unreachable)
        return self


class CanonicalEffectKey(StrictModel):
    """UEA 类型去重使用的规范化五元组。"""

    source: ResourceRef | None
    action: CapabilityAction
    sink: ResourceRef
    scope: Scope
    lifetime: Lifetime


class EffectPathEvidence(StrictModel):
    """一个来源节点到 Effect 节点的脱敏可审计路径。"""

    node_ids: tuple[NonEmptyStr, ...]
    evidence_event_ids: tuple[NonEmptyStr, ...]
    boundary_depth: BoundaryDepth


class UnauthorizedEffectEvidence(StrictModel):
    """一个未授权且已执行 Effect 的理由、路径与稳定 ID。"""

    effect_id: NonEmptyStr
    receipt_id: NonEmptyStr
    decision_id: NonEmptyStr
    reason_codes: Annotated[tuple[PolicyReasonCode, ...], Field(min_length=1)]
    canonical_key: CanonicalEffectKey
    paths: Annotated[tuple[EffectPathEvidence, ...], Field(min_length=1)]
    evidence_ids: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]


class UeaMetricSummary(StrictModel):
    """UEA 实例数、全局类型数、主权重及其全部证据。"""

    uea_count: NonNegativeInt
    uea_type_count: NonNegativeInt
    uea_weight: NonNegativeFloat
    evidence_ids: tuple[NonEmptyStr, ...]
    canonical_effect_keys: tuple[CanonicalEffectKey, ...]


class ProvenanceCounts(StrictModel):
    """来源集合比较的 TP、FP、FN 原始计数。"""

    tp: NonNegativeInt
    fp: NonNegativeInt
    fn: NonNegativeInt
    artifact_ids: tuple[NonEmptyStr, ...]


class ProvenanceMetricSet(StrictModel):
    """同一聚合范围内的来源混淆计数与三类比例。"""

    counts: ProvenanceCounts
    precision: RatioMetric
    recall: RatioMetric
    f1: RatioMetric


class ProvenanceDepthMetrics(StrictModel):
    """一个边界总深度上的来源指标和相邻深度衰减。"""

    boundary_depth: NonNegativeInt
    metrics: ProvenanceMetricSet
    decay: SignedRatioMetric


class ProvenanceMetricSummary(StrictModel):
    """单场景或 micro 范围的总体与逐深度来源指标。"""

    overall: ProvenanceMetricSet
    by_boundary_depth: tuple[ProvenanceDepthMetrics, ...]
