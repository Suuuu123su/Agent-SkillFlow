"""从受控仓库相对路径加载 Scenario Manifest。"""

from pathlib import Path

from skillflow.models.manifest import SkillManifest
from skillflow.models.scenario import Scenario
from skillflow.oracle.models import OracleManifestPlan
from skillflow.validation import DocumentValidationError, ValidationIssue, validate_yaml_document


def load_oracle_manifests(
    scenario_path: Path,
    scenario: Scenario,
) -> tuple[OracleManifestPlan, ...]:
    """在 Scenario 所在仓库祖先中解析受控 Manifest 引用。"""
    bindings: list[OracleManifestPlan] = []
    for skill in scenario.skills:
        manifest_path = _find_relative_file(scenario_path, skill.manifest.root)
        manifest = validate_yaml_document(manifest_path, SkillManifest)
        bindings.append(OracleManifestPlan(skill.id, manifest))
    return tuple(bindings)


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
