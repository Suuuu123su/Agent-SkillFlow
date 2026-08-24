"""Experiment Matrix 的受控开关模型。"""

from typing import Annotated, Self

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.enums import EnforcementMode, ProvenanceMode
from skillflow.models.references import ScenarioPath


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


class ExperimentMatrix(StrictModel):
    """一组 ID 唯一的实验配置。"""

    schema_version: NonEmptyStr
    id: NonEmptyStr
    variants: Annotated[tuple[ExperimentVariant, ...], Field(min_length=1)]

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
