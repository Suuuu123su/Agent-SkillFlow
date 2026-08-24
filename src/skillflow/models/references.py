"""Scenario DSL 中受控的声明式引用。"""

import re
from typing import Final

from pydantic import ConfigDict, RootModel, field_validator
from pydantic_core import PydanticCustomError

MANIFEST_PATTERN: Final = re.compile(r"scenarios/manifests/[A-Za-z0-9][A-Za-z0-9._/-]*\.ya?ml")
SCENARIO_PATTERN: Final = re.compile(r"scenarios/[A-Za-z0-9][A-Za-z0-9._/-]*\.ya?ml")
FIXTURE_PATTERN: Final = re.compile(r"fixture://[A-Za-z0-9][A-Za-z0-9._/-]*")
ALIAS_PATTERN: Final = re.compile(r"[a-z][a-z0-9_-]*")


def _reference_error(code: str, reason: str) -> PydanticCustomError:
    return PydanticCustomError(code, "{reason}", {"reason": reason})


class ManifestPath(RootModel[str]):
    """只能指向 Scenario 受控 manifests 目录的相对路径。"""

    model_config = ConfigDict(frozen=True)

    @field_validator("root")
    @classmethod
    def validate_manifest_path(cls, value: str) -> str:
        """拒绝绝对路径、路径穿越和 manifests 目录外引用。"""
        normalized = value.strip()
        if "\\" in normalized or ".." in normalized.split("/"):
            raise _reference_error("manifest_path_unsafe", "manifest 路径禁止穿越或反斜线")
        if MANIFEST_PATTERN.fullmatch(normalized) is None:
            raise _reference_error(
                "manifest_path_outside_registry",
                "manifest 必须位于 scenarios/manifests/ 且为 YAML 文件",
            )
        return normalized


class FixtureImplementationRef(RootModel[str]):
    """只能由固定 fixture registry 解析的实现引用。"""

    model_config = ConfigDict(frozen=True)

    @field_validator("root")
    @classmethod
    def validate_fixture_reference(cls, value: str) -> str:
        """拒绝文件路径、模块路径和路径穿越。"""
        normalized = value.strip()
        if "\\" in normalized or ".." in normalized.split("/")[2:]:
            raise _reference_error("fixture_reference_unsafe", "fixture 引用禁止路径穿越")
        if FIXTURE_PATTERN.fullmatch(normalized) is None:
            raise _reference_error(
                "fixture_reference_invalid",
                "implementation 必须是 fixture://<registry-id>",
            )
        return normalized


class ScenarioPath(RootModel[str]):
    """Experiment Matrix 中受控的 Scenario 相对路径。"""

    model_config = ConfigDict(frozen=True)

    @field_validator("root")
    @classmethod
    def validate_scenario_path(cls, value: str) -> str:
        """拒绝 Scenario 根目录外的路径。"""
        normalized = value.strip()
        if "\\" in normalized or ".." in normalized.split("/"):
            raise _reference_error("scenario_path_unsafe", "scenario 路径禁止穿越或反斜线")
        if SCENARIO_PATTERN.fullmatch(normalized) is None:
            raise _reference_error(
                "scenario_path_outside_registry",
                "scenario 必须是 scenarios/ 下的 YAML 相对路径",
            )
        return normalized


class ArtifactAliasRef(RootModel[str]):
    """Scenario 内已声明 Artifact output 的引用。"""

    model_config = ConfigDict(frozen=True)

    @field_validator("root")
    @classmethod
    def validate_alias(cls, value: str) -> str:
        """要求 artifact:<alias> 形式。"""
        alias = value.removeprefix("artifact:")
        if not value.startswith("artifact:") or ALIAS_PATTERN.fullmatch(alias) is None:
            raise _reference_error("artifact_alias_invalid", "Artifact 引用必须是 artifact:<alias>")
        return value

    @property
    def alias(self) -> str:
        """返回不含命名空间前缀的别名。"""
        return self.root.removeprefix("artifact:")


class EffectSelectorRef(RootModel[str]):
    """Scenario 内已声明 effect selector 的引用。"""

    model_config = ConfigDict(frozen=True)

    @field_validator("root")
    @classmethod
    def validate_alias(cls, value: str) -> str:
        """要求 effect-selector:<alias> 形式。"""
        alias = value.removeprefix("effect-selector:")
        if not value.startswith("effect-selector:") or ALIAS_PATTERN.fullmatch(alias) is None:
            raise _reference_error(
                "effect_selector_alias_invalid",
                "Effect selector 引用必须是 effect-selector:<alias>",
            )
        return value

    @property
    def alias(self) -> str:
        """返回不含命名空间前缀的别名。"""
        return self.root.removeprefix("effect-selector:")


class OriginRef(RootModel[str]):
    """来源断言中的 asset 或 skill 引用。"""

    model_config = ConfigDict(frozen=True)

    @field_validator("root")
    @classmethod
    def validate_origin(cls, value: str) -> str:
        """要求 asset:<id> 或 skill:<id>。"""
        for prefix in ("asset:", "skill:"):
            if value.startswith(prefix) and ALIAS_PATTERN.fullmatch(value.removeprefix(prefix)):
                return value
        raise _reference_error(
            "origin_reference_invalid", "来源引用必须是 asset:<id> 或 skill:<id>"
        )

    @property
    def identifier(self) -> str:
        """返回来源 ID。"""
        return self.root.split(":", maxsplit=1)[1]


class ScenarioTargetRef(RootModel[str]):
    """Oracle 可观察的 Artifact 或 effect selector 引用。"""

    model_config = ConfigDict(frozen=True)

    @field_validator("root")
    @classmethod
    def validate_target(cls, value: str) -> str:
        """限定可观察引用的命名空间。"""
        for prefix in ("artifact:", "effect-selector:"):
            if value.startswith(prefix) and ALIAS_PATTERN.fullmatch(value.removeprefix(prefix)):
                return value
        raise _reference_error(
            "scenario_target_invalid",
            "观察目标必须是 artifact:<alias> 或 effect-selector:<alias>",
        )

    @property
    def alias(self) -> str:
        """返回不含命名空间前缀的别名。"""
        return self.root.split(":", maxsplit=1)[1]
