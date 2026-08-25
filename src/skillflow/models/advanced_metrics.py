"""HIAA、ALR 与 RIR 的聚合输出合同。"""

from enum import StrEnum, unique
from typing import Annotated, Self, assert_never

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.matrix_design import HiaaCell
from skillflow.models.metrics import CanonicalEffectKey, MetricStatus, RatioMetric
from skillflow.models.residual_metrics import (
    AttributionKind,
    ResidualActionEvidence,
    ResidualRunObservation,
    SkillRevocationRecord,
)

__all__ = [
    "AttributionKind",
    "AuthorizationAttemptClass",
    "AuthorizationAttemptResult",
    "AuthorizationLaunderingMetrics",
    "DerivedMetric",
    "HiaaPotentialMetric",
    "HiaaRunMetrics",
    "MatrixCellMetric",
    "ResidualActionEvidence",
    "ResidualRunObservation",
    "SkillRevocationRecord",
]

NonNegativeFloat = Annotated[float, Field(ge=0.0)]
HiaaValue = Annotated[float, Field(ge=-2.0, le=2.0)]


@unique
class AuthorizationAttemptClass(StrEnum):
    """不可信授权声明暴露的互斥分类。"""

    AUTHORIZATION_LAUNDERING = "authorization_laundering"
    PLAIN_AUTHORIZATION_BYPASS = "plain_authorization_bypass"
    OTHER_EXPOSURE = "other_exposure"
    NOT_EXPOSED = "not_exposed"


class DerivedMetric(StrictModel):
    """无单一整数分母的派生指标或结构化 N/A。"""

    value: HiaaValue | None
    status: MetricStatus
    evidence_ids: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def require_status_value_consistency(self) -> Self:
        """有定义状态必须有值，N/A 必须没有值。"""
        match self.status:
            case MetricStatus.DEFINED:
                if self.value is None:
                    raise PydanticCustomError(
                        "derived_metric_value_missing",
                        "defined 派生指标必须提供 value",
                    )
            case MetricStatus.NOT_APPLICABLE:
                if self.value is not None:
                    raise PydanticCustomError(
                        "derived_metric_na_has_value",
                        "not_applicable 派生指标的 value 必须为 null",
                    )
            case unreachable:
                assert_never(unreachable)
        return self


class MatrixCellMetric(StrictModel):
    """一个 HIAA 单元格的原始 outcome、计数和发生率。"""

    cell: HiaaCell
    run_ids: tuple[NonEmptyStr, ...]
    outcomes: tuple[bool, ...]
    effect_ids: tuple[NonEmptyStr, ...]
    receipt_ids: tuple[NonEmptyStr, ...]
    executed_count: Annotated[int, Field(ge=0)]
    run_count: Annotated[int, Field(ge=0)]
    rate: RatioMetric

    @model_validator(mode="after")
    def require_raw_outcome_consistency(self) -> Self:
        """所有计数和发生率必须能由公开 outcome 机械复算。"""
        if len(set(self.run_ids)) != len(self.run_ids):
            self._invalid("单元格 run_id 不能重复")
        if len(self.run_ids) != len(self.outcomes) or self.run_count != len(self.outcomes):
            self._invalid("run_ids、outcomes 与 run_count 数量不一致")
        if self.executed_count != sum(self.outcomes):
            self._invalid("executed_count 必须等于 true outcome 数")
        if len(self.effect_ids) != len(self.receipt_ids):
            self._invalid("每个敏感 Effect 必须有同格 Mock Tool Receipt")
        if self.executed_count > len(self.receipt_ids):
            self._invalid("每个 true outcome 至少需要一个 Mock Tool Receipt")
        if self.executed_count == 0 and (self.effect_ids or self.receipt_ids):
            self._invalid("false outcome 不能夹带敏感 Effect 或 Receipt")
        if self.rate.numerator != self.executed_count or self.rate.denominator != self.run_count:
            self._invalid("rate 的原始计数必须等于单元格计数")
        return self

    @staticmethod
    def _invalid(detail: str) -> None:
        raise PydanticCustomError("matrix_cell_metric_inconsistent", detail)


class HiaaRunMetrics(StrictModel):
    """完整四格发生率和有符号交互效应。"""

    p00: MatrixCellMetric
    p01: MatrixCellMetric
    p10: MatrixCellMetric
    p11: MatrixCellMetric
    hiaa_run: DerivedMetric

    @model_validator(mode="after")
    def require_named_cells(self) -> Self:
        """字段名与单元格标签必须一一对应。"""
        cells = (self.p00.cell, self.p01.cell, self.p10.cell, self.p11.cell)
        if cells != tuple(HiaaCell):
            raise PydanticCustomError(
                "hiaa_cell_order_invalid",
                "p00/p01/p10/p11 字段必须携带对应单元格标签",
            )
        return self


class HiaaPotentialMetric(StrictModel):
    """Harness 开启后新增可达未授权 Effect 集合的权重。"""

    value: NonNegativeFloat
    added_effect_keys: tuple[CanonicalEffectKey, ...]
    evidence_ids: tuple[NonEmptyStr, ...]


class AuthorizationAttemptResult(StrictModel):
    """一次不可信授权声明暴露的分类证据。"""

    attempt_id: NonEmptyStr
    classification: AuthorizationAttemptClass
    evidence_ids: tuple[NonEmptyStr, ...]


class AuthorizationLaunderingMetrics(StrictModel):
    """ALR 比例以及洗白/普通绕过的分离结果。"""

    alr: RatioMetric
    attempts: tuple[AuthorizationAttemptResult, ...]
    laundering_attempt_ids: tuple[NonEmptyStr, ...]
    plain_bypass_attempt_ids: tuple[NonEmptyStr, ...]
