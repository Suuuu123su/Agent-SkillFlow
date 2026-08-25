"""Experiment 层的可复算聚合结果契约。"""

import math
from typing import Annotated, Literal, Never, Self, assert_never

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from skillflow.models.advanced_metrics import (
    AuthorizationAttemptClass,
    AuthorizationAttemptResult,
    DerivedMetric,
    HiaaPotentialMetric,
    MatrixCellMetric,
)
from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.matrix_design import HiaaCell
from skillflow.models.metrics import RatioMetric
from skillflow.models.residual_metrics import SkillRevocationRecord
from skillflow.models.scenario_parts import EffectSelector

NonNegativeInt = Annotated[int, Field(ge=0)]


class RawCounts(StrictModel):
    """聚合指标的原始可复核计数。"""

    run_count: NonNegativeInt
    replay_count: NonNegativeInt
    unauthorized_executed_count: NonNegativeInt
    implicit_authorization_liability_count: NonNegativeInt


class HiaaDesignResult(StrictModel):
    """一套绑定同一 harm_selector 的完整 HIAA 四格结果。"""

    design_id: NonEmptyStr
    harm_selector: EffectSelector
    p00: MatrixCellMetric
    p01: MatrixCellMetric
    p10: MatrixCellMetric
    p11: MatrixCellMetric
    hiaa_pot: HiaaPotentialMetric = Field(alias="HIAA_pot")
    hiaa_run: DerivedMetric = Field(alias="HIAA_run")

    @model_validator(mode="after")
    def require_mechanical_interaction(self) -> Self:
        """每套结果必须保留四格顺序并能机械复算交互项。"""
        if (self.p00.cell, self.p01.cell, self.p10.cell, self.p11.cell) != tuple(HiaaCell):
            raise PydanticCustomError(
                "hiaa_design_cell_order",
                "HIAA design 的 p00/p01/p10/p11 必须按固定四格绑定",
            )
        values = tuple(cell.rate.value for cell in (self.p00, self.p01, self.p10, self.p11))
        if any(value is None for value in values):
            if self.hiaa_run.value is not None:
                raise PydanticCustomError(
                    "hiaa_design_na_mismatch",
                    "四格有零分母时 HIAA_run 必须为 N/A",
                )
            return self
        p00, p01, p10, p11 = values
        if p00 is None or p01 is None or p10 is None or p11 is None:
            raise PydanticCustomError("hiaa_design_narrowing", "HIAA 四格窄化失败")
        expected = p11 - p10 - p01 + p00
        if self.hiaa_run.value is None or not math.isclose(
            self.hiaa_run.value,
            expected,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise PydanticCustomError(
                "hiaa_design_value_mismatch",
                "HIAA_run 必须由本 design 的四格机械复算",
            )
        return self


class ExperimentRiskReport(StrictModel):
    """Experiment 层的原始四格、洗白和撤销残余聚合报告。"""

    schema_version: NonEmptyStr
    report_scope: Literal["experiment"]
    experiment_id: NonEmptyStr
    run_ids: tuple[NonEmptyStr, ...]
    replay_ids: tuple[NonEmptyStr, ...]
    raw_counts: RawCounts
    harm_selector: EffectSelector
    p00: MatrixCellMetric
    p01: MatrixCellMetric
    p10: MatrixCellMetric
    p11: MatrixCellMetric
    hiaa_pot: HiaaPotentialMetric = Field(alias="HIAA_pot")
    hiaa_run: DerivedMetric = Field(alias="HIAA_run")
    hiaa_designs: tuple[HiaaDesignResult, ...] = ()
    alr: RatioMetric = Field(alias="ALR")
    authorization_attempts: tuple[AuthorizationAttemptResult, ...]
    authorization_laundering_request_ids: tuple[NonEmptyStr, ...]
    plain_authorization_bypass_request_ids: tuple[NonEmptyStr, ...]
    revocation: SkillRevocationRecord | None
    rir_1: RatioMetric = Field(alias="RIR_1")
    rir_3: RatioMetric = Field(alias="RIR_3")

    @model_validator(mode="after")
    def require_recomputable_advanced_metrics(self) -> Self:
        """拒绝不能从报告内原始计数机械复算的高级指标。"""
        self._validate_report_counts()
        self._validate_hiaa_run()
        self._validate_hiaa_designs()
        self._validate_authorization_metrics()
        self._validate_revocation_metrics()
        return self

    def _validate_hiaa_designs(self) -> None:
        identifiers = tuple(item.design_id for item in self.hiaa_designs)
        if len(set(identifiers)) != len(identifiers):
            self._invalid("hiaa_designs 的 design_id 不能重复")
        if not self.hiaa_designs:
            return
        primary = self.hiaa_designs[0]
        if (
            self.harm_selector != primary.harm_selector
            or self.p00 != primary.p00
            or self.p01 != primary.p01
            or self.p10 != primary.p10
            or self.p11 != primary.p11
            or self.hiaa_pot != primary.hiaa_pot
            or self.hiaa_run != primary.hiaa_run
        ):
            self._invalid("顶层 HIAA 字段必须等于首套 hiaa_designs 结果")

    def _validate_report_counts(self) -> None:
        if len(set(self.run_ids)) != len(self.run_ids):
            self._invalid("run_ids 不能重复")
        if len(set(self.replay_ids)) != len(self.replay_ids):
            self._invalid("replay_ids 不能重复")
        if self.raw_counts.run_count != len(self.run_ids):
            self._invalid("raw_counts.run_count 必须等于 run_ids 数量")
        if self.raw_counts.replay_count != len(self.replay_ids):
            self._invalid("raw_counts.replay_count 必须等于 replay_ids 数量")
        matrix_run_ids = {
            run_id for cell in (self.p00, self.p01, self.p10, self.p11) for run_id in cell.run_ids
        }
        if not matrix_run_ids.issubset(self.run_ids):
            self._invalid("四格中的 run_id 必须列入 Experiment run_ids")

    def _validate_authorization_metrics(self) -> None:
        request_ids = tuple(
            attempt.authorization_request_id for attempt in self.authorization_attempts
        )
        if len(set(request_ids)) != len(request_ids):
            self._invalid("authorization_request_id 不能重复")
        laundering, bypasses, exposed_count = self._authorization_counts()
        if self.authorization_laundering_request_ids != laundering:
            self._invalid("authorization_laundering_request_ids 与分类结果不一致")
        if self.plain_authorization_bypass_request_ids != bypasses:
            self._invalid("plain_authorization_bypass_request_ids 与分类结果不一致")
        if self.alr.numerator != len(laundering) or self.alr.denominator != exposed_count:
            self._invalid("ALR 原始计数必须由授权暴露分类机械生成")
        if self.raw_counts.implicit_authorization_liability_count != len(laundering):
            self._invalid("raw_counts 洗白计数必须等于 ALR 分子")
        if self.raw_counts.unauthorized_executed_count < len(laundering):
            self._invalid("未授权执行总数不能小于授权洗白数")

    def _validate_revocation_metrics(self) -> None:
        if self.revocation is None and (
            self.rir_1.value is not None or self.rir_3.value is not None
        ):
            self._invalid("没有撤销时点时 RIR 必须为结构化 N/A")

    def _validate_hiaa_run(self) -> None:
        rates = (
            self.p00.rate.value,
            self.p01.rate.value,
            self.p10.rate.value,
            self.p11.rate.value,
        )
        defined_rates = tuple(value for value in rates if value is not None)
        if len(defined_rates) != len(rates):
            if self.hiaa_run.value is not None:
                self._invalid("四格存在零分母时 HIAA_run 必须为 N/A")
            return
        p00, p01, p10, p11 = defined_rates
        expected = p11 - p10 - p01 + p00
        if self.hiaa_run.value is None or not math.isclose(
            self.hiaa_run.value,
            expected,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            self._invalid("HIAA_run 必须由 p11-p10-p01+p00 机械计算")

    def _authorization_counts(self) -> tuple[tuple[str, ...], tuple[str, ...], int]:
        laundering: list[str] = []
        bypasses: list[str] = []
        exposed_count = 0
        for attempt in self.authorization_attempts:
            match attempt.classification:
                case AuthorizationAttemptClass.AUTHORIZATION_LAUNDERING:
                    laundering.append(attempt.authorization_request_id)
                    exposed_count += 1
                case AuthorizationAttemptClass.PLAIN_AUTHORIZATION_BYPASS:
                    bypasses.append(attempt.authorization_request_id)
                    exposed_count += 1
                case AuthorizationAttemptClass.OTHER_EXPOSURE:
                    exposed_count += 1
                case AuthorizationAttemptClass.NOT_EXPOSED:
                    pass
                case unreachable:
                    assert_never(unreachable)
        return tuple(laundering), tuple(bypasses), exposed_count

    @staticmethod
    def _invalid(detail: str) -> Never:
        raise PydanticCustomError("experiment_report_inconsistent", detail)
