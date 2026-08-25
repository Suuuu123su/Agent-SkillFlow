"""Experiment Matrix 的受控开关模型与 HIAA 四格生成器。"""

from typing import Annotated, Self, assert_never

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.enums import EnforcementMode, ProvenanceMode
from skillflow.models.matrix_design import (
    HarnessFeature,
    HiaaCell,
    HiaaDesign,
    NeutralSkillPair,
    SkillControlProfile,
    SkillLengthInterval,
)
from skillflow.models.references import ScenarioPath

__all__ = [
    "ExperimentMatrix",
    "ExperimentVariant",
    "HarnessFeature",
    "HiaaCell",
    "HiaaDesign",
    "NeutralSkillPair",
    "SkillControlProfile",
    "SkillLengthInterval",
    "build_hiaa_matrix",
]


class ExperimentVariant(StrictModel):
    """一个 Scenario 与受控 Harness 开关的确定性配置。"""

    variant: NonEmptyStr
    scenario: ScenarioPath
    seed: int
    target_skill_present: bool
    shared_context: bool
    persistent_memory: bool
    auto_approve_tools: bool
    enforcement_mode: EnforcementMode
    provenance_mode: ProvenanceMode
    implicit_text_authorization: bool
    hiaa_cell: HiaaCell | None = None


class ExperimentMatrix(StrictModel):
    """一组 ID 唯一的实验配置。"""

    schema_version: NonEmptyStr
    id: NonEmptyStr
    variants: Annotated[tuple[ExperimentVariant, ...], Field(min_length=1)]
    hiaa_design: HiaaDesign | None = None

    @model_validator(mode="after")
    def reject_duplicate_variants(self) -> Self:
        """同一矩阵中 variant ID 必须唯一。"""
        identifiers = tuple(variant.variant for variant in self.variants)
        if len(set(identifiers)) != len(identifiers):
            raise PydanticCustomError(
                "matrix_variant_duplicate",
                "Experiment Matrix 存在重复 variant ID",
            )
        return self

    @model_validator(mode="after")
    def require_exact_generated_hiaa_cells(self) -> Self:
        """带 HIAA 设计的矩阵必须与机械生成的四格逐字段一致。"""
        if self.hiaa_design is None:
            if any(variant.hiaa_cell is not None for variant in self.variants):
                raise PydanticCustomError(
                    "matrix_hiaa_design_missing",
                    "带 hiaa_cell 的矩阵必须声明 hiaa_design",
                )
            return self
        if self.variants != _hiaa_variants(self.hiaa_design):
            raise PydanticCustomError(
                "matrix_hiaa_cells_inconsistent",
                "HIAA 四格必须由 hiaa_design 机械生成且只改变两个受控因素",
            )
        return self


def build_hiaa_matrix(design: HiaaDesign) -> ExperimentMatrix:
    """从能力匹配的 Skill 对自动生成 p00/p01/p10/p11。"""
    return ExperimentMatrix(
        schema_version=design.schema_version,
        id=design.id,
        variants=_hiaa_variants(design),
        hiaa_design=design,
    )


def _hiaa_variants(design: HiaaDesign) -> tuple[ExperimentVariant, ...]:
    return tuple(_hiaa_variant(design, cell) for cell in HiaaCell)


def _hiaa_variant(design: HiaaDesign, cell: HiaaCell) -> ExperimentVariant:
    target_present = cell in {HiaaCell.P10, HiaaCell.P11}
    feature_enabled = cell in {HiaaCell.P01, HiaaCell.P11}
    shared_context = design.shared_context
    persistent_memory = design.persistent_memory
    auto_approve_tools = design.auto_approve_tools
    implicit_text_authorization = design.implicit_text_authorization
    match design.feature:
        case HarnessFeature.SHARED_CONTEXT:
            shared_context = feature_enabled
        case HarnessFeature.PERSISTENT_MEMORY:
            persistent_memory = feature_enabled
        case HarnessFeature.AUTO_APPROVE_TOOLS:
            auto_approve_tools = feature_enabled
        case HarnessFeature.IMPLICIT_TEXT_AUTHORIZATION:
            implicit_text_authorization = feature_enabled
        case unreachable:
            assert_never(unreachable)
    return ExperimentVariant(
        variant=cell.value,
        scenario=design.target_scenario if target_present else design.neutral_scenario,
        seed=design.seed,
        target_skill_present=target_present,
        shared_context=shared_context,
        persistent_memory=persistent_memory,
        auto_approve_tools=auto_approve_tools,
        enforcement_mode=design.enforcement_mode,
        provenance_mode=design.provenance_mode,
        implicit_text_authorization=implicit_text_authorization,
        hiaa_cell=cell,
    )
