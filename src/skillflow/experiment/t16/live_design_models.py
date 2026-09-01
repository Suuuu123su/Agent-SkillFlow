"""T16-C 模型不可见元数据与模型输入的数据结构。"""

import json
from typing import Annotated, Literal, Self, TypedDict

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from skillflow.experiment.t16.live_tools import LiveToolName
from skillflow.experiment.t16.openai_output_schemas import ResponseOutputContract
from skillflow.experiment.t16.openai_response_models import JsonObject
from skillflow.experiment.t16.preregistration_models import (
    IndependentFactor,
    PairRole,
    T16Intervention,
)
from skillflow.models.authorization import AuthorizationGrant
from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.matrix_design import HiaaCell
from skillflow.models.references import EffectSelectorRef, ScenarioPath
from skillflow.models.scenario_parts import EffectSelector


class BaseDesignFields(TypedDict):
    """所有条件构造器共享且类型封闭的 Trial 元数据。"""

    matrix_trial_id: str
    scenario: ScenarioPath
    condition_id: str
    semantic_instance_id: str
    pair_id: str
    repeat_index: int
    task_prompt: str
    pair_role: PairRole
    independent_factor: IndependentFactor
    hiaa_cell: HiaaCell | None
    harm_selector: EffectSelectorRef | None
    observation_sessions: tuple[int, ...]
    intervention: T16Intervention


class LiveEffectAliasBinding(StrictModel):
    """模型可见中性别名与 Scenario 实际 selector 的单向绑定。"""

    public_alias: NonEmptyStr
    actual_alias: NonEmptyStr


class LiveCapabilityContext(StrictModel):
    """模型可见的原始能力事实；不包含授权或结果判定。"""

    schema_version: Literal["0.2"] = "0.2"
    session_index: Annotated[int, Field(ge=0)]
    skill_ids: tuple[NonEmptyStr, ...]
    asset_ids: tuple[NonEmptyStr, ...]
    tool_names: tuple[LiveToolName, ...]
    grants: tuple[AuthorizationGrant, ...]
    effect_selectors: tuple[EffectSelector, ...]


class LiveSessionDesign(StrictModel):
    """一个需要真实模型判断的本地安全 Session。"""

    session_index: Annotated[int, Field(ge=0)]
    capability_context: LiveCapabilityContext
    input_items: Annotated[tuple[JsonObject, ...], Field(min_length=1)]
    tool_names: tuple[LiveToolName, ...]
    effect_alias_bindings: tuple[LiveEffectAliasBinding, ...] = ()
    allowed_effect_aliases: frozenset[NonEmptyStr] = frozenset()
    required_tool_names: tuple[LiveToolName, ...] = ()
    output_contract: ResponseOutputContract = ResponseOutputContract.FINISH_V2

    @property
    def expected_target_effect_aliases(self) -> tuple[str, ...]:
        """返回当前 Session 允许落地的 Scenario 实际 selector。"""
        return tuple(item.actual_alias for item in self.effect_alias_bindings)

    @model_validator(mode="after")
    def require_context_matches_session(self) -> Self:
        """拒绝模型可见能力上下文与实际 Session Tool 漂移。"""
        if self.capability_context.session_index != self.session_index:
            raise PydanticCustomError(
                "t16_live_context_session_mismatch",
                "能力上下文 Session 索引与实际 Session 不一致",
            )
        if self.capability_context.tool_names != self.tool_names:
            raise PydanticCustomError(
                "t16_live_context_tools_mismatch",
                "能力上下文 Tool 与实际 Session 不一致",
            )
        public_aliases = tuple(item.public_alias for item in self.effect_alias_bindings)
        actual_aliases = tuple(item.actual_alias for item in self.effect_alias_bindings)
        if len(set(public_aliases)) != len(public_aliases) or len(set(actual_aliases)) != len(
            actual_aliases
        ):
            raise PydanticCustomError(
                "t16_live_effect_alias_binding_duplicate",
                "Effect 公共别名与实际别名在同一 Session 内必须唯一",
            )
        if self.allowed_effect_aliases != frozenset(public_aliases):
            raise PydanticCustomError(
                "t16_live_allowed_effect_alias_mismatch",
                "Session 允许的 Effect 必须精确等于公共别名绑定",
            )
        context_aliases = tuple(item.alias for item in self.capability_context.effect_selectors)
        if context_aliases != public_aliases:
            raise PydanticCustomError(
                "t16_live_public_effect_selector_mismatch",
                "模型可见 selector 必须精确使用当前 Session 公共别名",
            )
        return self


class LiveTrialDesign(StrictModel):
    """模型不可见元数据与模型可见操纵的显式分离。"""

    matrix_trial_id: NonEmptyStr
    scenario: ScenarioPath
    condition_id: NonEmptyStr
    semantic_instance_id: NonEmptyStr
    pair_id: NonEmptyStr
    repeat_index: Annotated[int, Field(ge=1)]
    task_prompt: NonEmptyStr
    pair_role: PairRole
    independent_factor: IndependentFactor
    hiaa_cell: HiaaCell | None = None
    harm_selector: EffectSelectorRef | None = None
    target_effect_aliases: tuple[NonEmptyStr, ...] = ()
    observation_sessions: tuple[Annotated[int, Field(ge=0)], ...] = ()
    authorization_request_id: NonEmptyStr | None = None
    structured_target_authorized: bool = False
    decision_basis_artifact_ids: tuple[NonEmptyStr, ...] = ()
    baseline_reason: NonEmptyStr | None = None
    intervention: T16Intervention = T16Intervention.NONE
    skill_artifact_text: NonEmptyStr | None = None
    shared_context_text: NonEmptyStr | None = None
    artifact_text: NonEmptyStr | None = None
    assets: dict[NonEmptyStr, NonEmptyStr]
    sessions: Annotated[tuple[LiveSessionDesign, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def require_trial_alias_and_session_consistency(self) -> Self:
        """拒绝跨 Session 公共别名重映射和目标 selector 漂移。"""
        session_indices = tuple(item.session_index for item in self.sessions)
        if len(set(session_indices)) != len(session_indices) or session_indices != tuple(
            sorted(session_indices)
        ):
            raise PydanticCustomError(
                "t16_live_design_session_order",
                "Live Session 索引必须唯一且按时序递增",
            )
        catalog: dict[str, str] = {}
        actual_aliases: list[str] = []
        for session in self.sessions:
            for binding in session.effect_alias_bindings:
                previous = catalog.setdefault(binding.public_alias, binding.actual_alias)
                if previous != binding.actual_alias:
                    raise PydanticCustomError(
                        "t16_live_public_alias_remapped",
                        "同一公共 Effect 别名不得跨 Session 映射到不同实际 selector",
                    )
                if binding.actual_alias not in actual_aliases:
                    actual_aliases.append(binding.actual_alias)
        if tuple(actual_aliases) != self.target_effect_aliases:
            raise PydanticCustomError(
                "t16_live_target_effect_alias_mismatch",
                "Trial 目标 selector 必须精确等于 Session 实际 selector 绑定",
            )
        by_index = {item.session_index: item for item in self.sessions}
        if any(index not in by_index for index in self.observation_sessions):
            raise PydanticCustomError(
                "t16_live_observation_session_missing",
                "观察索引必须绑定真实 Live Session",
            )
        if any(
            not by_index[index].expected_target_effect_aliases
            for index in self.observation_sessions
        ):
            raise PydanticCustomError(
                "t16_live_observation_selector_missing",
                "观察 Session 必须声明实际目标 selector",
            )
        return self

    def serialized_model_input(self) -> str:
        """仅序列化 API 将看到的内容，用于标签泄露检查。"""
        return json.dumps(
            [item for session in self.sessions for item in session.input_items],
            ensure_ascii=False,
            separators=(",", ":"),
        )
