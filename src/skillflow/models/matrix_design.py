"""HIAA 四格实验的受控设计与能力匹配对照。"""

from enum import StrEnum, unique
from typing import Annotated, Self

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.enums import EnforcementMode, ProvenanceMode
from skillflow.models.references import ScenarioPath

NonNegativeInt = Annotated[int, Field(ge=0)]


@unique
class HiaaCell(StrEnum):
    """目标 Skill 与 Harness 特性的四格组合。"""

    P00 = "p00"
    P01 = "p01"
    P10 = "p10"
    P11 = "p11"


@unique
class HarnessFeature(StrEnum):
    """首版可做开关对照的 Harness 布尔特性。"""

    SHARED_CONTEXT = "shared_context"
    PERSISTENT_MEMORY = "persistent_memory"
    AUTO_APPROVE_TOOLS = "auto_approve_tools"
    IMPLICIT_TEXT_AUTHORIZATION = "implicit_text_authorization"


class SkillControlProfile(StrictModel):
    """一个 Skill 在中和配对中必须公开的结构控制量。"""

    skill_id: NonEmptyStr
    manifest_sha256: NonEmptyStr
    schema_sha256: NonEmptyStr
    tool_registrations: tuple[NonEmptyStr, ...]
    content_length: NonNegativeInt
    dangerous_semantics_present: bool

    @model_validator(mode="after")
    def reject_duplicate_tool_registrations(self) -> Self:
        """工具注册集合不能靠重复项伪造长度匹配。"""
        if len(set(self.tool_registrations)) != len(self.tool_registrations):
            raise PydanticCustomError(
                "skill_control_tool_duplicate",
                "Skill 工具注册存在重复项",
            )
        return self


class SkillLengthInterval(StrictModel):
    """目标与中性 Skill 必须共同落入的预注册长度区间。"""

    minimum: NonNegativeInt
    maximum: NonNegativeInt

    @model_validator(mode="after")
    def require_ordered_interval(self) -> Self:
        """长度区间下界不得大于上界。"""
        if self.minimum > self.maximum:
            raise PydanticCustomError(
                "skill_length_interval_reversed",
                "Skill 长度区间下界不能大于上界",
            )
        return self


class NeutralSkillPair(StrictModel):
    """除危险语义外保持 Manifest、Schema、工具与长度匹配的 Skill 对。"""

    target: SkillControlProfile
    neutral: SkillControlProfile
    length_interval: SkillLengthInterval

    @model_validator(mode="after")
    def require_capability_matched_neutral(self) -> Self:
        """拒绝通过削弱中性 Skill 结构制造虚假 HIAA。"""
        if self.target.skill_id == self.neutral.skill_id:
            self._invalid("目标与中性 Skill 必须使用不同 ID")
        if not self.target.dangerous_semantics_present:
            self._invalid("目标 Skill 必须明确包含待中和的危险语义")
        if self.neutral.dangerous_semantics_present:
            self._invalid("中性 Skill 必须明确移除危险语义")
        if self.target.manifest_sha256 != self.neutral.manifest_sha256:
            self._invalid("中性 Skill 必须保持相同 Manifest")
        if self.target.schema_sha256 != self.neutral.schema_sha256:
            self._invalid("中性 Skill 必须保持相同 Schema")
        if set(self.target.tool_registrations) != set(self.neutral.tool_registrations):
            self._invalid("中性 Skill 必须保持相同工具注册")
        lengths = (self.target.content_length, self.neutral.content_length)
        if any(
            length < self.length_interval.minimum or length > self.length_interval.maximum
            for length in lengths
        ):
            self._invalid("目标与中性 Skill 必须位于同一预注册长度区间")
        return self

    @staticmethod
    def _invalid(detail: str) -> None:
        raise PydanticCustomError("neutral_skill_control_mismatch", detail)


class HiaaDesign(StrictModel):
    """自动生成四格矩阵所需的全部预注册控制条件。"""

    schema_version: NonEmptyStr
    id: NonEmptyStr
    target_scenario: ScenarioPath
    neutral_scenario: ScenarioPath
    seed: int
    feature: HarnessFeature
    skill_pair: NeutralSkillPair
    shared_context: bool
    persistent_memory: bool
    auto_approve_tools: bool
    enforcement_mode: EnforcementMode
    provenance_mode: ProvenanceMode
    implicit_text_authorization: bool
