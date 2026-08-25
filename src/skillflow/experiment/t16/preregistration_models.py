"""T16 真实模型实验的预注册边界模型。"""

from dataclasses import dataclass
from enum import StrEnum, unique
from typing import Annotated, Literal, Self, assert_never

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.enums import CapabilityAction
from skillflow.models.matrix_design import HiaaCell
from skillflow.models.references import EffectSelectorRef, ManifestPath, ScenarioPath

NonNegativeInt = Annotated[int, Field(ge=0)]


@unique
class PairRole(StrEnum):
    """一个条件在能力匹配组中的角色。"""

    STANDALONE = "standalone"
    TARGET = "target"
    NEUTRAL = "neutral"
    STRUCTURED_CONTROL = "structured_control"


@unique
class IndependentFactor(StrEnum):
    """能力匹配组唯一允许改变的因素。"""

    NONE = "none"
    SKILL_SEMANTICS = "skill_semantics"
    MEMORY_SEMANTICS = "memory_semantics"
    AUTHORIZATION_SOURCE = "authorization_source"


@unique
class T16Intervention(StrEnum):
    """条件级预注册干预。"""

    NONE = "none"
    NEUTRALIZE_AUTHORIZATION_CLAIM = "neutralize_authorization_claim"


class SemanticTemplate(StrictModel):
    """一个语义等价、表述不同的任务模板。"""

    template_id: NonEmptyStr
    task_prompt: NonEmptyStr


class SemanticInstanceSet(StrictModel):
    """一组固定十条的语义等价模板。"""

    instance_set_id: NonEmptyStr
    templates: Annotated[tuple[SemanticTemplate, ...], Field(min_length=10, max_length=10)]

    @model_validator(mode="after")
    def reject_duplicate_templates(self) -> Self:
        """每个模板 ID 在集合内必须唯一。"""
        identifiers = tuple(item.template_id for item in self.templates)
        if len(set(identifiers)) != len(identifiers):
            raise PydanticCustomError("t16_template_duplicate", "语义模板 ID 不能重复")
        return self


class PayloadLengthBand(StrictModel):
    """能力匹配输入共同使用的 UTF-8 字节长度区间。"""

    minimum: NonNegativeInt
    maximum: NonNegativeInt

    @model_validator(mode="after")
    def require_ordered_band(self) -> Self:
        """长度区间必须有序。"""
        if self.minimum > self.maximum:
            raise PydanticCustomError("t16_length_band_reversed", "输入长度区间下界不能大于上界")
        return self


class CapabilityProfile(StrictModel):
    """配对条件必须保持的 Skill、Manifest、Tool 与输入结构。"""

    skill_ids: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
    manifest_paths: Annotated[tuple[ManifestPath, ...], Field(min_length=1)]
    tool_actions: tuple[CapabilityAction, ...]
    authorization_structure_id: NonEmptyStr
    data_format: NonEmptyStr
    payload: NonEmptyStr
    payload_length_band: PayloadLengthBand

    @model_validator(mode="after")
    def require_auditable_profile(self) -> Self:
        """拒绝重复能力和伪造的长度声明。"""
        if len(self.skill_ids) != len(self.manifest_paths):
            raise PydanticCustomError("t16_skill_manifest_count", "Skill 与 Manifest 必须逐项对齐")
        if len(set(self.skill_ids)) != len(self.skill_ids):
            raise PydanticCustomError("t16_skill_duplicate", "Skill ID 不能重复")
        if len(set(self.manifest_paths)) != len(self.manifest_paths):
            raise PydanticCustomError("t16_manifest_duplicate", "Manifest 路径不能重复")
        if len(set(self.tool_actions)) != len(self.tool_actions):
            raise PydanticCustomError("t16_tool_action_duplicate", "Tool action 不能重复")
        payload_length = len(self.payload.encode("utf-8"))
        if not (
            self.payload_length_band.minimum <= payload_length <= self.payload_length_band.maximum
        ):
            raise PydanticCustomError("t16_payload_length_mismatch", "payload 不在预注册长度区间")
        return self


class T16Condition(StrictModel):
    """T16 的一个实验条件。"""

    condition_id: NonEmptyStr
    scenario: ScenarioPath
    pair_group_id: NonEmptyStr
    pair_role: PairRole
    independent_factor: IndependentFactor
    instance_set_id: NonEmptyStr
    capability: CapabilityProfile
    intervention: T16Intervention = T16Intervention.NONE
    observation_sessions: tuple[NonNegativeInt, ...] = ()
    hiaa_cell: HiaaCell | None = None
    hiaa_design_id: NonEmptyStr | None = None
    harm_selector: EffectSelectorRef | None = None

    @model_validator(mode="after")
    def require_condition_controls(self) -> Self:
        """HIAA 绑定和会话观察必须完整且无重复。"""
        if tuple(sorted(set(self.observation_sessions))) != self.observation_sessions:
            raise PydanticCustomError("t16_observation_sessions", "观察 Session 必须升序且不重复")
        hiaa_values = (self.hiaa_design_id, self.harm_selector)
        if self.hiaa_cell is None and any(value is not None for value in hiaa_values):
            raise PydanticCustomError("t16_hiaa_cell_missing", "HIAA 设计必须绑定四格 cell")
        if self.hiaa_cell is not None and any(value is None for value in hiaa_values):
            raise PydanticCustomError(
                "t16_hiaa_binding_missing",
                "HIAA cell 必须绑定 design 和 selector",
            )
        return self


@dataclass(frozen=True, slots=True)
class _CapabilityPair:
    """一次能力匹配比较所需的完整输入。"""

    left: CapabilityProfile
    right: CapabilityProfile
    factor: IndependentFactor


class T16Preregistration(StrictModel):
    """12 条件、10 实例、3 重复的冻结实验设计。"""

    schema_version: Literal["0.1"]
    id: NonEmptyStr
    semantic_instances_per_condition: Literal[10] = 10
    repeats_per_instance: Literal[3] = 3
    model2_subset_template_ids: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
    instance_sets: Annotated[tuple[SemanticInstanceSet, ...], Field(min_length=1)]
    conditions: Annotated[tuple[T16Condition, ...], Field(min_length=12, max_length=12)]

    @model_validator(mode="after")
    def require_closed_design(self) -> Self:
        """验证引用、能力匹配组和 HIAA 四格。"""
        set_ids = tuple(item.instance_set_id for item in self.instance_sets)
        condition_ids = tuple(item.condition_id for item in self.conditions)
        if len(set(set_ids)) != len(set_ids):
            self._invalid("instance_set_id 不能重复")
        if len(set(condition_ids)) != len(condition_ids):
            self._invalid("condition_id 不能重复")
        declared_sets = set(set_ids)
        if any(item.instance_set_id not in declared_sets for item in self.conditions):
            self._invalid("condition 引用了未声明的 instance_set_id")
        for instance_set in self.instance_sets:
            available = {item.template_id for item in instance_set.templates}
            if not set(self.model2_subset_template_ids).issubset(available):
                self._invalid("第二模型抽样模板必须存在于每个实例集合")
        self._validate_pair_groups()
        self._validate_hiaa_designs()
        return self

    def _validate_pair_groups(self) -> None:
        groups: dict[str, list[T16Condition]] = {}
        for condition in self.conditions:
            groups.setdefault(condition.pair_group_id, []).append(condition)
        for group in groups.values():
            self._validate_pair_group(group)

    def _validate_pair_group(self, group: list[T16Condition]) -> None:
        if len(group) == 1:
            item = group[0]
            if item.pair_role is not PairRole.STANDALONE:
                self._invalid("单条件组必须标记为 standalone")
            if item.independent_factor is not IndependentFactor.NONE:
                self._invalid("单条件组不得声明配对自变量")
            return
        factors = {item.independent_factor for item in group}
        if len(factors) != 1:
            self._invalid("同一能力匹配组必须共享唯一自变量")
        factor = next(iter(factors))
        roles = {item.pair_role for item in group}
        if PairRole.TARGET not in roles or PairRole.NEUTRAL not in roles:
            self._invalid("能力匹配组必须同时包含 target 与 neutral")
        if len(roles) != len(group):
            self._invalid("能力匹配组的角色不能重复")
        if len({item.instance_set_id for item in group}) != 1:
            self._invalid("能力匹配组必须共享语义实例集合")
        reference = group[0].capability
        for condition in group[1:]:
            self._validate_profile_pair(
                _CapabilityPair(
                    left=reference,
                    right=condition.capability,
                    factor=factor,
                )
            )

    @classmethod
    def _validate_profile_pair(cls, pair: _CapabilityPair) -> None:
        left = pair.left
        right = pair.right
        common = (
            left.skill_ids == right.skill_ids
            and left.manifest_paths == right.manifest_paths
            and set(left.tool_actions) == set(right.tool_actions)
            and left.data_format == right.data_format
            and left.payload_length_band == right.payload_length_band
        )
        if not common:
            cls._invalid("target/neutral 的 Tool、Skill、Manifest、格式或长度不匹配")
        match pair.factor:
            case IndependentFactor.SKILL_SEMANTICS | IndependentFactor.MEMORY_SEMANTICS:
                if left.authorization_structure_id != right.authorization_structure_id:
                    cls._invalid("授权不是自变量时必须保持相同授权结构")
            case IndependentFactor.AUTHORIZATION_SOURCE:
                pass
            case IndependentFactor.NONE:
                cls._invalid("多条件能力匹配组不能使用 none 自变量")
            case unreachable:
                assert_never(unreachable)

    def _validate_hiaa_designs(self) -> None:
        designs: dict[str, list[T16Condition]] = {}
        for condition in self.conditions:
            if condition.hiaa_design_id is not None:
                designs.setdefault(condition.hiaa_design_id, []).append(condition)
        for group in designs.values():
            cells = tuple(item.hiaa_cell for item in group)
            if set(cells) != set(HiaaCell) or len(cells) != len(HiaaCell):
                self._invalid("每套 HIAA 必须精确包含 p00/p01/p10/p11")
            if len({item.harm_selector for item in group}) != 1:
                self._invalid("每套 HIAA 四格必须共享同一 harm_selector")

    @staticmethod
    def _invalid(detail: str) -> None:
        raise PydanticCustomError("t16_preregistration_inconsistent", detail)

    @property
    def primary_trial_count(self) -> int:
        """返回单模型完整矩阵链数。"""
        return (
            len(self.conditions) * self.semantic_instances_per_condition * self.repeats_per_instance
        )
