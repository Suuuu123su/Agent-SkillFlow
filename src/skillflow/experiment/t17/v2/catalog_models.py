"""技能版本身份及能力匹配合同；家族标签不参与结果判定。"""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from skillflow.benchmark.scripted_backend import FixtureScript
from skillflow.experiment.t17.minimal.contracts import Sha256
from skillflow.experiment.t17.v2.frozen import relative_path
from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.effects import CapabilityEffect
from skillflow.models.enums import Decision
from skillflow.models.matrix import ExperimentVariant
from skillflow.models.scenario_parts import EffectSelector


class SkillBundle(StrictModel):
    """声明式技能文件；只能调用已登记工具，不能导入或执行代码。"""

    schema_version: Literal["2.0"] = "2.0"
    bundle_id: NonEmptyStr
    scripts: dict[NonEmptyStr, FixtureScript]
    decisions: dict[NonEmptyStr, Decision] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_fixture_boundary(self) -> Self:
        """限制实现地址及动作身份，执行仍由受信工具代理完成。"""
        if not self.scripts or any(not key.startswith("fixture://") for key in self.scripts):
            raise ValueError("v2_bundle_fixture_required")
        for script in self.scripts.values():
            identifiers = tuple(action.action_id for action in script.actions)
            if len(set(identifiers)) != len(identifiers):
                raise ValueError("v2_bundle_duplicate_action")
            keys = {a.decision_key for a in script.actions} | {
                a.input_gate.mismatch_decision_key
                for a in script.actions
                if a.input_gate is not None
            }
            if not keys <= self.decisions.keys():
                raise ValueError("v2_bundle_decision_missing")
        return self


class SkillVariant(StrictModel):
    """足以固定运行输入并支持后续留出技能比较的身份。"""

    schema_version: Literal["2.0"] = "2.0"
    skill_variant_id: NonEmptyStr
    skill_family: NonEmptyStr
    attack_family: NonEmptyStr
    variant_role: Literal["attack", "neutral", "benign-control"]
    skill_version: NonEmptyStr
    source_path: NonEmptyStr
    scenario_path: NonEmptyStr
    scenario_sha256: Sha256
    skill_content_sha256: Sha256
    manifest_paths: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
    manifest_sha256: Sha256
    capability_fingerprint: Sha256
    tool_registry_fingerprint: Sha256
    input_schema_fingerprint: Sha256
    output_schema_fingerprint: Sha256
    task_contract_id: NonEmptyStr
    neutral_pair_skill_id: NonEmptyStr | None
    pair_id: NonEmptyStr | None
    risk_effect_selector: tuple[EffectSelector, ...]
    harness_factor: tuple[NonEmptyStr, ...]
    scope_requirements: tuple[CapabilityEffect, ...]
    lifetime_requirements: tuple[NonEmptyStr, ...]
    split: Literal["development", "validation", "held-out"]

    @model_validator(mode="after")
    def validate_identity_paths(self) -> Self:
        """公开目录不得含宿主路径或自行与自身配对。"""
        for path in (self.source_path, self.scenario_path, *self.manifest_paths):
            relative_path(path)
        if self.neutral_pair_skill_id == self.skill_variant_id:
            raise ValueError("v2_catalog_self_pair")
        if self.neutral_pair_skill_id is not None and (
            self.variant_role != "attack" or self.pair_id is None
        ):
            raise ValueError("v2_catalog_pair_role")
        return self


_MATCHED_FIELDS = (
    "manifest_sha256",
    "capability_fingerprint",
    "tool_registry_fingerprint",
    "input_schema_fingerprint",
    "output_schema_fingerprint",
    "task_contract_id",
    "scope_requirements",
    "lifetime_requirements",
    "skill_version",
    "pair_id",
    "split",
)


class CatalogCondition(StrictModel):
    """目录中一项技能在预注册环境下的任务配置。"""

    skill_variant_id: NonEmptyStr
    configuration: ExperimentVariant


class SkillCatalog(StrictModel):
    """配对必须能力相同；不同内容、版本和实验角色始终可追踪。"""

    schema_version: Literal["2.0"] = "2.0"
    catalog_id: NonEmptyStr
    variants: Annotated[tuple[SkillVariant, ...], Field(min_length=1)]
    conditions: tuple[CatalogCondition, ...] = ()

    @model_validator(mode="after")
    def validate_pairs(self) -> Self:
        """先拒绝重号及不匹配目录，再允许生成任何任务。"""
        entries = {item.skill_variant_id: item for item in self.variants}
        if len(entries) != len(self.variants):
            raise ValueError("v2_catalog_duplicate_skill")
        identifiers = tuple(item.configuration.variant for item in self.conditions)
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("v2_catalog_duplicate_condition")
        for condition in self.conditions:
            skill = entries.get(condition.skill_variant_id)
            if skill is None or condition.configuration.scenario.root != skill.scenario_path:
                raise ValueError("v2_catalog_condition_binding")
        for attack in self.variants:
            if attack.neutral_pair_skill_id is None:
                continue
            neutral = entries.get(attack.neutral_pair_skill_id)
            if neutral is None:
                raise ValueError("v2_catalog_pair_missing")
            _validate_capability_pair(attack, neutral)
        return self


def _validate_capability_pair(attack: SkillVariant, neutral: SkillVariant) -> None:
    if neutral.variant_role != "neutral":
        raise ValueError("v2_catalog_pair_role")
    for field in _MATCHED_FIELDS:
        if getattr(attack, field) != getattr(neutral, field):
            raise ValueError("v2_catalog_capability_mismatch:" + field)
