"""撤销时点与严格可归因残余动作的数据合同。"""

from datetime import datetime
from enum import StrEnum, unique
from typing import Annotated, Self, assert_never

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from skillflow.models.base import NonEmptyStr, StrictModel

NonNegativeInt = Annotated[int, Field(ge=0)]


@unique
class AttributionKind(StrEnum):
    """RIR 唯一接受的两类归因证据及显式无归因状态。"""

    INFLUENCE_CONFIRMED = "INFLUENCE_CONFIRMED"
    GT_INFLUENCE = "GT_influence"
    NONE = "none"


class ResidualActionEvidence(StrictModel):
    """撤销后一次动作的授权真值与归因证据。"""

    effect_id: NonEmptyStr
    receipt_id: NonEmptyStr
    unauthorized: bool
    attribution: AttributionKind
    attributed_skill_id: NonEmptyStr | None = None
    attribution_evidence_ids: tuple[NonEmptyStr, ...] = ()
    oracle_provenance_evidence_ids: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def require_typed_attribution_evidence(self) -> Self:
        """因果归因必须独立成证；Oracle 来源路径只能作为非因果辅助证据。"""
        match self.attribution:
            case AttributionKind.INFLUENCE_CONFIRMED | AttributionKind.GT_INFLUENCE:
                if self.attributed_skill_id is None:
                    raise PydanticCustomError(
                        "rir_attributed_skill_missing",
                        "RIR 严格归因必须指明 attributed_skill_id",
                    )
                if not self.attribution_evidence_ids:
                    raise PydanticCustomError(
                        "rir_attribution_evidence_missing",
                        "RIR 归因必须提供 INFLUENCE_CONFIRMED 或独立 GT_influence 证据 ID",
                    )
            case AttributionKind.NONE:
                if self.attributed_skill_id is not None or self.attribution_evidence_ids:
                    raise PydanticCustomError(
                        "rir_none_has_evidence",
                        "无归因状态不能携带 Skill ID 或归因证据",
                    )
            case unreachable:
                assert_never(unreachable)
        return self


class ResidualRunObservation(StrictModel):
    """一个撤销后候选测试 Run 的结构化结果。"""

    run_id: NonEmptyStr
    session_index: NonNegativeInt
    started_at: datetime
    valid: bool
    actions: tuple[ResidualActionEvidence, ...] = ()

    @model_validator(mode="after")
    def require_timezone(self) -> Self:
        """RIR 时序比较拒绝无时区时间。"""
        if self.started_at.tzinfo is None:
            raise PydanticCustomError(
                "rir_run_timezone_missing",
                "Residual Run started_at 必须包含时区",
            )
        return self


class SkillRevocationRecord(StrictModel):
    """计算会话偏移所需的不可变 Skill 撤销时点。"""

    skill_id: NonEmptyStr
    revoke_event_id: NonEmptyStr
    session_index: NonNegativeInt
    revoked_at: datetime

    @model_validator(mode="after")
    def require_timezone(self) -> Self:
        """撤销时间必须能与运行时间确定比较。"""
        if self.revoked_at.tzinfo is None:
            raise PydanticCustomError(
                "rir_revoke_timezone_missing",
                "revoked_at 必须包含时区",
            )
        return self
