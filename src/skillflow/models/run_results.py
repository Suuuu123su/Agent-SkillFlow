"""T13 标准 RunResult 中的结构化执行证据。"""

from datetime import datetime
from typing import Annotated, Self

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.effects import CapabilityEffect
from skillflow.models.enums import Decision, TrustLevel

NonNegativeInt = Annotated[int, Field(ge=0)]


class DecisionBasisArtifact(StrictModel):
    """一个进入 Decision 依据的脱敏 Artifact。"""

    artifact_id: NonEmptyStr
    aliases: tuple[NonEmptyStr, ...] = ()
    trust: TrustLevel


class RunEffectResult(StrictModel):
    """一个 Receipt 锚定 Effect 的决策、会话与授权事实。"""

    effect_id: NonEmptyStr
    effect_alias: NonEmptyStr | None = None
    selector_aliases: tuple[NonEmptyStr, ...] = ()
    action_id: NonEmptyStr
    request_event_id: NonEmptyStr
    decision_id: NonEmptyStr
    actor_id: NonEmptyStr
    session_id: NonEmptyStr
    session_index: NonNegativeInt
    timestamp: datetime
    effect: CapabilityEffect
    authorized: bool
    baseline_result: Decision
    policy_result: Decision
    executed: bool
    receipt_id: NonEmptyStr
    decision_basis_artifacts: tuple[DecisionBasisArtifact, ...] = ()
    matched_grant_ids: tuple[NonEmptyStr, ...] = ()
    reason_codes: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def require_executed_receipt(self) -> Self:
        """RunEffectResult 只表示带真实 Receipt 的已执行 Effect。"""
        if not self.executed:
            raise PydanticCustomError(
                "run_effect_not_executed",
                "RunEffectResult 必须是 executed=true 的 Receipt Effect",
            )
        return self


class ArtifactAliasEvidence(StrictModel):
    """反事实目标 alias 与当前 Run Artifact 的脱敏绑定。"""

    alias: NonEmptyStr
    artifact_id: NonEmptyStr
    trust: TrustLevel


class RunRevocationEvidence(StrictModel):
    """一个 Skill 撤销事件及其 Scenario Session 索引。"""

    skill_id: NonEmptyStr
    revoke_event_id: NonEmptyStr
    session_index: NonNegativeInt
    revoked_at: datetime
