"""Skill Manifest 输入模型。"""

from typing import Literal, Self

from pydantic import model_validator
from pydantic_core import PydanticCustomError

from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.effects import CapabilityEffect
from skillflow.models.enums import PrincipalType


class SkillManifest(StrictModel):
    """Skill 声明的能力上限，不包含真实 Grant。"""

    schema_version: NonEmptyStr
    id: NonEmptyStr
    principal_type: Literal[PrincipalType.SKILL] = PrincipalType.SKILL
    description: str = ""
    requested_permissions: tuple[CapabilityEffect, ...] = ()
    declared_permissions: tuple[CapabilityEffect, ...] = ()

    @model_validator(mode="after")
    def reject_ambiguous_permission_fields(self) -> Self:
        """允许两种兼容字段名，但禁止同时声明两份能力。"""
        if self.requested_permissions and self.declared_permissions:
            raise PydanticCustomError(
                "manifest_permissions_ambiguous",
                "requested_permissions 与 declared_permissions 不能同时非空",
            )
        return self
