"""T17 证据域、Hook 能力与统一测量状态。"""

import math
from dataclasses import dataclass
from enum import StrEnum, unique
from typing import Annotated, Never, Self, assert_never

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from skillflow.models.base import NonEmptyStr, StrictModel

NonNegativeInt = Annotated[int, Field(ge=0)]
UnitInterval = Annotated[float, Field(ge=0.0, le=1.0)]


@unique
class MeasurementStatus(StrEnum):
    """T17 把已测、设计不适用、Hook 缺失和阶段不完整分开。"""

    MEASURED = "measured"
    NOT_APPLICABLE = "not_applicable"
    NOT_AVAILABLE = "not_available"
    INCOMPLETE = "incomplete"


@unique
class EvidenceDomainKind(StrEnum):
    """禁止直接 micro 聚合的实验执行域。"""

    CONTRACT = "contract"
    SCRIPTED = "scripted"
    FAKE_PROVIDER = "fake_provider"
    DIRECT_PROMPT = "direct_prompt"
    REFERENCE_HARNESS = "reference_harness"
    OPENCLAW = "openclaw"


@unique
class HookName(StrEnum):
    """T17 Reference Harness 必须显式声明的证据 Hook。"""

    AUTHORIZATION = "authorization"
    DECISION_BASIS = "decision_basis"
    PROVENANCE = "provenance"
    INFLUENCE = "influence"
    REVOCATION = "revocation"
    TASK_SUCCESS = "task_success"


class EvidenceDomain(StrictModel):
    """一次可聚合实验的协议、Harness 与模型身份。"""

    domain_id: NonEmptyStr
    kind: EvidenceDomainKind
    protocol_id: NonEmptyStr
    simulation_only: bool
    external_effects_simulated: bool
    provider: NonEmptyStr | None = None
    model_id: NonEmptyStr | None = None
    model_revision: NonEmptyStr | None = None

    @model_validator(mode="after")
    def require_complete_model_identity(self) -> Self:
        """模型字段必须同时存在或同时缺失。"""
        identity = (self.provider, self.model_id, self.model_revision)
        if any(item is None for item in identity) and any(item is not None for item in identity):
            raise PydanticCustomError(
                "t17_evidence_domain_partial_model",
                "provider、model_id 与 model_revision 必须同时存在",
            )
        return self


@dataclass(frozen=True, slots=True)
class EvidenceDomainMismatchError(ValueError):
    """待聚合记录来自多个 Evidence Domain。"""

    domain_ids: tuple[str, ...]

    def __str__(self) -> str:
        """返回不包含正文的稳定诊断。"""
        return f"禁止跨 Evidence Domain micro 聚合: {', '.join(self.domain_ids)}"


def require_single_evidence_domain(domains: tuple[EvidenceDomain, ...]) -> EvidenceDomain:
    """只接受非空且完全相同的 Evidence Domain 集合。"""
    if not domains:
        raise EvidenceDomainMismatchError(())
    first = domains[0]
    if any(item != first for item in domains[1:]):
        raise EvidenceDomainMismatchError(tuple(item.domain_id for item in domains))
    return first


class HookCapability(StrictModel):
    """一个场景对单项受信 Hook 的需求与实际可用性。"""

    hook: HookName
    required: bool
    available: bool
    status: MeasurementStatus
    reason: NonEmptyStr | None = None
    evidence_ids: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def require_consistent_status(self) -> Self:
        """Hook 状态必须与 required/available 事实一致。"""
        expected = _hook_status(self.required, self.available, self.status)
        if self.status is not expected:
            raise PydanticCustomError(
                "t17_hook_status_mismatch",
                "Hook status 与 required/available 不一致",
            )
        if self.status is not MeasurementStatus.MEASURED and self.reason is None:
            raise PydanticCustomError(
                "t17_hook_reason_missing",
                "非 measured Hook 必须提供 reason",
            )
        return self


def _hook_status(
    required: bool,
    available: bool,
    declared: MeasurementStatus,
) -> MeasurementStatus:
    if not required:
        return MeasurementStatus.NOT_APPLICABLE
    if not available:
        return MeasurementStatus.NOT_AVAILABLE
    if declared is MeasurementStatus.INCOMPLETE:
        return MeasurementStatus.INCOMPLETE
    return MeasurementStatus.MEASURED


class RatioMeasurement(StrictModel):
    """保留 scheduled/observed 计数且禁止把缺失证据伪装为零。"""

    status: MeasurementStatus
    numerator: NonNegativeInt | None = None
    denominator: NonNegativeInt | None = None
    scheduled_denominator: NonNegativeInt | None = None
    value: UnitInterval | None = None
    reason: NonEmptyStr | None = None
    evidence_ids: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def require_consistent_measurement(self) -> Self:
        """按四态合同验证数值、计数和原因。"""
        match self.status:
            case MeasurementStatus.MEASURED:
                self._require_measured()
            case MeasurementStatus.INCOMPLETE:
                self._require_incomplete()
            case MeasurementStatus.NOT_APPLICABLE | MeasurementStatus.NOT_AVAILABLE:
                if any(
                    item is not None
                    for item in (
                        self.numerator,
                        self.denominator,
                        self.scheduled_denominator,
                        self.value,
                    )
                ):
                    self._invalid("N/A 比例不得携带数值或计数")
                if self.reason is None:
                    self._invalid("N/A 比例必须说明原因")
            case unreachable:
                assert_never(unreachable)
        return self

    def _require_measured(self) -> None:
        numerator = self.numerator
        denominator = self.denominator
        value = self.value
        if numerator is None or denominator is None or value is None:
            self._invalid("measured 比例窄化失败")
        if denominator == 0:
            self._invalid("measured 比例要求非零分母")
        if numerator > denominator:
            self._invalid("比例分子不能大于分母")
        if self.scheduled_denominator not in {None, denominator}:
            self._invalid("完整测量的 scheduled 分母必须等于 observed 分母")
        expected = numerator / denominator
        if not math.isclose(value, expected, rel_tol=1e-12, abs_tol=1e-12):
            self._invalid("value 必须等于 numerator / denominator")

    def _require_incomplete(self) -> None:
        numerator = self.numerator
        denominator = self.denominator
        scheduled = self.scheduled_denominator
        if numerator is None or denominator is None or scheduled is None:
            self._invalid("incomplete 比例窄化失败")
        if numerator > denominator or denominator >= scheduled:
            self._invalid("incomplete 比例必须满足 numerator<=observed<scheduled")
        if self.value is not None or self.reason is None:
            self._invalid("incomplete 比例不得发布 value 且必须说明原因")

    @staticmethod
    def _invalid(detail: str) -> Never:
        raise PydanticCustomError("t17_ratio_inconsistent", detail)
