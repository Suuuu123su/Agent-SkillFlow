"""T16-B 双 Fake Slot 配置与逐链记录边界。"""

from enum import StrEnum, unique
from pathlib import Path
from typing import Annotated, Final, Literal, Self

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from skillflow.experiment.t16.budget import BudgetConfig
from skillflow.experiment.t16.preregistration_models import (
    IndependentFactor,
    PairRole,
    T16Intervention,
)
from skillflow.experiment.t16.provider import (
    PricingRates,
    PricingStatus,
    ProviderConfig,
    ProviderKind,
    TokenUsage,
)
from skillflow.experiment.t16.trial import TrialResult
from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.matrix_design import HiaaCell
from skillflow.models.references import EffectSelectorRef
from skillflow.validation import validate_yaml_document

PositiveInt = Annotated[int, Field(ge=1)]

A1_PRESERVED_FIELDS: Final = (
    "tool_actions",
    "skill_ids",
    "manifest_paths",
    "authorization_structure_id",
    "data_format",
    "payload_length_band",
    "task_prompt",
)


@unique
class CostChainProfile(StrEnum):
    """费用演练的三种链长。"""

    SHORT = "short"
    NORMAL = "normal"
    M2_MULTI_SESSION = "m2_multi_session"


class FakeModelSlot(StrictModel):
    """一个不对应真实厂商请求的逻辑模型槽位。"""

    slot_id: NonEmptyStr
    provider: ProviderConfig

    @model_validator(mode="after")
    def require_fake_provider(self) -> Self:
        """槽位只能绑定零费用 Fake Provider。"""
        if self.provider.kind is not ProviderKind.FAKE:
            raise PydanticCustomError("t16b_live_slot", "T16-B 槽位只能使用 Fake Provider")
        return self


class CostProfileDefinition(StrictModel):
    """一类链在正常和最坏情况下的模拟 Token 总量。"""

    profile: CostChainProfile
    normal_usage: TokenUsage
    worst_case_usage: TokenUsage
    normal_api_calls: PositiveInt
    worst_case_api_calls: PositiveInt


class T16BDryRunConfig(StrictModel):
    """T16-B 可复跑、默认禁 Live 的完整静态配置。"""

    schema_version: Literal["0.1"] = "0.1"
    id: NonEmptyStr
    slots: Annotated[tuple[FakeModelSlot, ...], Field(min_length=2, max_length=2)]
    budget: BudgetConfig
    rates_are_hypothetical: Literal[True] = True
    hypothetical_pricing: PricingRates
    cost_profiles: Annotated[tuple[CostProfileDefinition, ...], Field(min_length=3, max_length=3)]

    @model_validator(mode="after")
    def require_closed_fake_design(self) -> Self:
        """拒绝槽位重复、Live 开关或不完整费用画像。"""
        slot_ids = tuple(item.slot_id for item in self.slots)
        if len(set(slot_ids)) != len(slot_ids):
            raise PydanticCustomError("t16b_slot_duplicate", "Fake 模型槽位 ID 不能重复")
        if self.budget.allow_live:
            raise PydanticCustomError("t16b_live_enabled", "T16-B 必须保持 allow_live=false")
        if self.budget.max_retries != 1:
            raise PydanticCustomError("t16b_retry_not_one", "T16-B 只允许一次有限重试")
        if self.hypothetical_pricing.status is not PricingStatus.LIVE_PINNED:
            raise PydanticCustomError("t16b_hypothetical_pricing", "模拟价格必须显式冻结")
        profiles = tuple(item.profile for item in self.cost_profiles)
        if set(profiles) != set(CostChainProfile) or len(set(profiles)) != len(profiles):
            raise PydanticCustomError("t16b_cost_profiles", "费用画像必须精确覆盖三种链长")
        return self


class SessionEffectObservation(StrictModel):
    """M2 在一个预注册 Session 点的目标 Effect 结果。"""

    session_index: PositiveInt
    target_effect_requested: bool
    target_effect_executed: bool
    receipt_id: NonEmptyStr | None = None

    @model_validator(mode="after")
    def require_receipted_execution(self) -> Self:
        """Session 级执行事实也必须绑定 Receipt。"""
        if self.target_effect_executed != (self.receipt_id is not None):
            raise PydanticCustomError("t16b_session_receipt", "Session Effect 与 Receipt 不一致")
        if self.target_effect_executed and not self.target_effect_requested:
            raise PydanticCustomError("t16b_session_request", "Session Effect 执行前必须先请求")
        return self


class DryRunInterventionAudit(StrictModel):
    """记录中和实际删除和明确保持的字段。"""

    intervention: T16Intervention
    removed_fields: tuple[NonEmptyStr, ...]
    preserved_fields: tuple[NonEmptyStr, ...]

    @model_validator(mode="after")
    def require_claim_only_neutralization(self) -> Self:
        """A1 中和不得顺带改变 Tool、Skill、Manifest 或输入结构。"""
        if self.intervention is T16Intervention.NEUTRALIZE_AUTHORIZATION_CLAIM:
            if self.removed_fields != ("authorization_claim",):
                raise PydanticCustomError("t16b_a1_removed_fields", "A1 中和只允许删除授权声明")
            if self.preserved_fields != A1_PRESERVED_FIELDS:
                raise PydanticCustomError("t16b_a1_preserved_fields", "A1 中和缺少能力保持证据")
        elif self.removed_fields:
            raise PydanticCustomError("t16b_unregistered_removal", "未注册干预不得删除字段")
        return self


class DryRunTrialRecord(StrictModel):
    """720 条 Fake 链中一条可独立复验的操作记录。"""

    schema_version: Literal["0.1"] = "0.1"
    simulation_only: Literal[True] = True
    slot_id: NonEmptyStr
    matrix_trial_id: NonEmptyStr
    pair_role: PairRole
    independent_factor: IndependentFactor
    hiaa_cell: HiaaCell | None = None
    harm_selector: EffectSelectorRef | None = None
    session_observations: tuple[SessionEffectObservation, ...] = ()
    intervention_audit: DryRunInterventionAudit | None = None
    result: TrialResult

    @model_validator(mode="after")
    def require_fake_runtime_identity(self) -> Self:
        """运行身份、Fake Provider 与 HIAA 绑定必须一致。"""
        expected = f"{self.slot_id}--{self.matrix_trial_id}"
        if self.result.trial_id != expected:
            raise PydanticCustomError("t16b_runtime_trial_id", "运行 trial_id 未绑定槽位身份")
        if self.result.provider is not ProviderKind.FAKE:
            raise PydanticCustomError("t16b_nonfake_result", "Dry Run 结果必须来自 Fake Provider")
        if (self.hiaa_cell is None) != (self.harm_selector is None):
            raise PydanticCustomError("t16b_hiaa_binding", "HIAA cell 与 selector 必须同时存在")
        sessions = tuple(item.session_index for item in self.session_observations)
        if sessions != tuple(sorted(set(sessions))):
            raise PydanticCustomError("t16b_session_order", "Session 结果必须升序且不重复")
        return self


def load_t16b_config(path: Path) -> T16BDryRunConfig:
    """读取严格 T16-B Fake Dry Run 配置。"""
    return validate_yaml_document(path, T16BDryRunConfig)
