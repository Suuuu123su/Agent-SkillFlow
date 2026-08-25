"""T16 预注册加载与实际 Scenario/Manifest 绑定复核。"""

from dataclasses import dataclass
from pathlib import Path

from skillflow.experiment.t16.preregistration_models import T16Condition, T16Preregistration
from skillflow.models.enums import CapabilityAction
from skillflow.models.manifest import SkillManifest
from skillflow.models.scenario import Scenario
from skillflow.validation import validate_yaml_document


@dataclass(frozen=True, slots=True)
class PreregistrationBindingError(ValueError):
    """预注册能力声明与实际 Scenario 文件不一致。"""

    condition_id: str
    detail: str

    def __str__(self) -> str:
        """返回稳定诊断。"""
        return f"{self.condition_id}: {self.detail}"


def load_preregistration(path: Path) -> T16Preregistration:
    """读取严格 T16 预注册 YAML。"""
    return validate_yaml_document(path, T16Preregistration)


def verify_scenario_bindings(registration: T16Preregistration, project_root: Path) -> None:
    """用实际 Scenario 与 Manifest 复核自报能力合同。"""
    for condition in registration.conditions:
        scenario = validate_yaml_document(project_root / condition.scenario.root, Scenario)
        skill_ids = tuple(item.id for item in scenario.skills)
        manifest_paths = tuple(item.manifest for item in scenario.skills)
        if skill_ids != condition.capability.skill_ids:
            raise PreregistrationBindingError(condition.condition_id, "Skill ID 与 Scenario 不一致")
        if manifest_paths != condition.capability.manifest_paths:
            raise PreregistrationBindingError(condition.condition_id, "Manifest 与 Scenario 不一致")
        actions = _manifest_actions(condition, project_root)
        if actions != frozenset(condition.capability.tool_actions):
            raise PreregistrationBindingError(
                condition.condition_id,
                "Tool action 与 Manifest 不一致",
            )


def _manifest_actions(
    condition: T16Condition,
    project_root: Path,
) -> frozenset[CapabilityAction]:
    actions: set[CapabilityAction] = set()
    for reference in condition.capability.manifest_paths:
        manifest = validate_yaml_document(project_root / reference.root, SkillManifest)
        permissions = (*manifest.requested_permissions, *manifest.declared_permissions)
        actions.update(item.action for item in permissions)
    return frozenset(actions)
