"""从受控仓库相对路径加载 Scenario Manifest。"""

from dataclasses import dataclass
from pathlib import Path

from skillflow.models.manifest import SkillManifest
from skillflow.models.scenario import Scenario
from skillflow.oracle.models import OracleManifestPlan
from skillflow.validation import DocumentValidationError, ValidationIssue, validate_yaml_document


@dataclass(frozen=True, slots=True)
class ManifestBinding:
    """Scenario Skill 与已验证 Manifest 的中立绑定。"""

    skill_id: str
    manifest: SkillManifest


def load_manifests(
    scenario_path: Path,
    scenario: Scenario,
) -> tuple[ManifestBinding, ...]:
    """为 Runtime 与 Oracle 各自提供同一只读声明输入。"""
    bindings: list[ManifestBinding] = []
    for skill in scenario.skills:
        manifest_path = _find_relative_file(scenario_path, skill.manifest.root)
        manifest = validate_yaml_document(manifest_path, SkillManifest)
        if manifest.id != skill.id:
            raise DocumentValidationError(
                (
                    ValidationIssue(
                        file=manifest_path,
                        field_path="$.id",
                        code="manifest_skill_id_mismatch",
                        reason=f"Manifest ID 必须等于 Scenario Skill ID：{skill.id}",
                    ),
                )
            )
        bindings.append(ManifestBinding(skill.id, manifest))
    return tuple(bindings)


def load_oracle_manifests(
    scenario_path: Path,
    scenario: Scenario,
) -> tuple[OracleManifestPlan, ...]:
    """在 Scenario 所在仓库祖先中解析受控 Manifest 引用。"""
    return tuple(
        OracleManifestPlan(binding.skill_id, binding.manifest)
        for binding in load_manifests(scenario_path, scenario)
    )


def _find_relative_file(scenario_path: Path, relative_path: str) -> Path:
    resolved_scenario = scenario_path.resolve()
    for ancestor in resolved_scenario.parents:
        candidate = (ancestor / relative_path).resolve()
        if candidate.is_relative_to(ancestor) and candidate.is_file():
            return candidate
    missing = resolved_scenario.parent / relative_path
    raise DocumentValidationError(
        (
            ValidationIssue(
                file=missing,
                field_path="$.skills[*].manifest",
                code="manifest_file_missing",
                reason=f"未在 Scenario 仓库祖先中找到受控 Manifest：{relative_path}",
            ),
        )
    )
