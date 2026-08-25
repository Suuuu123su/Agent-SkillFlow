"""Scenario DSL 的组合组件。"""

from datetime import datetime
from enum import StrEnum, unique
from typing import Annotated, Literal, Self, assert_never

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from skillflow.models.authorization import AuthorizationGrant
from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.enums import (
    CapabilityAction,
    EnforcementMode,
    PrincipalType,
    ProvenanceMode,
    TrustLevel,
)
from skillflow.models.references import (
    ArtifactAliasRef,
    EffectSelectorRef,
    FixtureImplementationRef,
    ManifestPath,
    OriginRef,
    ScenarioTargetRef,
)
from skillflow.models.resources import ResourceRef


@unique
class StepAction(StrEnum):
    """Scripted Backend 唯一允许的声明式操作。"""

    INVOKE_SKILL = "invoke_skill"
    WRITE_MEMORY = "write_memory"
    READ_MEMORY = "read_memory"
    REQUEST_TOOL = "request_tool"
    USER_CONFIRM = "user_confirm"
    REVOKE_SKILL = "revoke_skill"
    UNLOAD_SKILL = "unload_skill"
    RESTART_RUNTIME = "restart_runtime"


class ClockSpec(StrictModel):
    """确定性虚拟时钟。"""

    start: datetime

    @model_validator(mode="after")
    def require_timezone(self) -> Self:
        """拒绝缺少时区的非确定时间。"""
        if self.start.tzinfo is None:
            raise PydanticCustomError("clock_timezone_missing", "clock.start 必须包含时区")
        return self


class TaskSpec(StrictModel):
    """Scenario 中唯一任务。"""

    id: NonEmptyStr
    prompt: NonEmptyStr


class AssetSpec(StrictModel):
    """每次 Run 复制到隔离 workspace 的输入资产。"""

    id: NonEmptyStr
    uri: ResourceRef
    trust: TrustLevel
    sensitivity: Annotated[int, Field(ge=0, le=4)] = 0
    marker: NonEmptyStr | None = None


class ScenarioSkill(StrictModel):
    """受控 Manifest 与 fixture 实现的绑定。"""

    id: NonEmptyStr
    manifest: ManifestPath
    implementation: FixtureImplementationRef


class HarnessConfig(StrictModel):
    """用于四格实验的 Harness 受控开关。"""

    shared_context: bool
    persistent_memory: bool
    auto_approve_tools: bool
    provenance_mode: ProvenanceMode
    implicit_text_authorization: bool = False


class ExecutionConfig(StrictModel):
    """运行期只观察或实际阻断。"""

    mode: EnforcementMode


class EffectSelector(StrictModel):
    """把运行期多个 EffectRecord 映射到稳定别名。"""

    alias: NonEmptyStr
    action: CapabilityAction
    source_pattern: ResourceRef | None
    sink_pattern: ResourceRef


class ScenarioStep(StrictModel):
    """Scripted Backend 的一个声明式步骤。"""

    id: NonEmptyStr
    action: StepAction
    skill: NonEmptyStr | None = None
    actor: PrincipalType | None = None
    outputs: tuple[ArtifactAliasRef, ...] = ()
    grant: AuthorizationGrant | None = None

    @model_validator(mode="after")
    def validate_action_contract(self) -> Self:
        """按封闭操作枚举验证主体和 Skill 引用。"""
        match self.action:
            case StepAction.INVOKE_SKILL:
                self._require_no_grant()
                if self.skill is None:
                    raise PydanticCustomError("step_skill_missing", "invoke_skill 要求 skill")
            case StepAction.WRITE_MEMORY | StepAction.READ_MEMORY | StepAction.REQUEST_TOOL:
                self._require_no_grant()
            case StepAction.USER_CONFIRM:
                self._require_trusted_actor()
                if self.grant is None:
                    raise PydanticCustomError(
                        "step_grant_missing",
                        "user_confirm 要求结构化 Grant",
                    )
                if self.grant.issuer_type is not self.actor:
                    raise PydanticCustomError(
                        "step_grant_issuer_mismatch",
                        "user_confirm actor 必须与 Grant issuer_type 一致",
                    )
            case StepAction.REVOKE_SKILL | StepAction.UNLOAD_SKILL:
                self._require_no_grant()
                self._require_trusted_actor()
                if self.skill is None:
                    raise PydanticCustomError("step_skill_missing", "撤销或卸载步骤要求 skill")
            case StepAction.RESTART_RUNTIME:
                self._require_no_grant()
            case _ as unreachable:
                assert_never(unreachable)
        return self

    def _require_trusted_actor(self) -> None:
        if self.actor not in {PrincipalType.USER, PrincipalType.TRUSTED_POLICY}:
            raise PydanticCustomError(
                "step_actor_untrusted",
                "该步骤要求 USER 或 TRUSTED_POLICY 可信主体",
            )

    def _require_no_grant(self) -> None:
        if self.grant is not None:
            raise PydanticCustomError(
                "step_grant_forbidden",
                "只有 user_confirm 可以携带 Grant",
            )


class SessionSpec(StrictModel):
    """一个有序 Session 步骤序列。"""

    id: NonEmptyStr
    steps: Annotated[tuple[ScenarioStep, ...], Field(min_length=1)]


class ForbiddenEffect(StrictModel):
    """Oracle 明确禁止的结构化效果。"""

    source: ResourceRef | None
    action: CapabilityAction
    sink: ResourceRef


class ExpectedOrigins(StrictModel):
    """Artifact 或 Effect 必须保留的来源集合。"""

    target: ScenarioTargetRef
    origins: Annotated[tuple[OriginRef, ...], Field(min_length=1)]


class ExpectedPersistence(StrictModel):
    """撤销后指定会话偏移上的持续影响预期。"""

    revoked_skill: NonEmptyStr
    check_offsets: Annotated[tuple[Annotated[int, Field(ge=1)], ...], Field(min_length=1)]


class OracleSpec(StrictModel):
    """Scenario 的结构化安全预期。"""

    forbidden_effects: tuple[ForbiddenEffect, ...] = ()
    expected_origins: tuple[ExpectedOrigins, ...] = ()
    expected_persistence: ExpectedPersistence | None = None


class CounterfactualSpec(StrictModel):
    """中和一个 Artifact 后观察 Effect 的反事实重放声明。"""

    target: ArtifactAliasRef
    intervention: Literal["neutralize"]
    observe: EffectSelectorRef
