"""T16 预注册加载与实际 Scenario/Manifest 绑定复核。"""

from dataclasses import dataclass
from pathlib import Path

from skillflow.experiment.t16.preregistration_models import T16Condition, T16Preregistration
from skillflow.models.authorization import AuthorizationGrant
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


def verify_scenario_bindings(
    registration: T16Preregistration,
    project_root: Path,
) -> dict[str, Scenario]:
    """用实际 Scenario 与 Manifest 复核自报能力合同并返回已验证绑定。"""
    scenarios: dict[str, Scenario] = {}
    for condition in registration.conditions:
        scenario = validate_yaml_document(project_root / condition.scenario.root, Scenario)
        scenarios[condition.condition_id] = scenario
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
        _verify_scenario_contract(condition, scenario)
    _verify_shared_grant_structures(registration, scenarios)
    _verify_pair_harnesses(registration, scenarios)
    _verify_pair_effect_selectors(registration, scenarios)
    _verify_pair_session_indices(registration, scenarios)
    return scenarios


def _verify_scenario_contract(condition: T16Condition, scenario: Scenario) -> None:
    declared_actions = frozenset(condition.capability.tool_actions)
    selector_actions = frozenset(item.action for item in scenario.effect_selectors)
    if not selector_actions.issubset(declared_actions):
        raise PreregistrationBindingError(
            condition.condition_id,
            "Effect selector action 不在预注册 Tool action 内",
        )
    grant_actions = frozenset(item.action for item in _scenario_grants(scenario))
    if not grant_actions.issubset(declared_actions):
        raise PreregistrationBindingError(
            condition.condition_id,
            "Authorization Grant action 不在预注册 Tool action 内",
        )
    selector_aliases = frozenset(item.alias for item in scenario.effect_selectors)
    if (
        condition.harm_selector is not None
        and condition.harm_selector.alias not in selector_aliases
    ):
        raise PreregistrationBindingError(
            condition.condition_id,
            "harm_selector 未绑定实际 Scenario effect selector",
        )
    invalid_sessions = tuple(
        index for index in condition.observation_sessions if index >= len(scenario.sessions)
    )
    if invalid_sessions:
        raise PreregistrationBindingError(
            condition.condition_id,
            f"观察 Session 索引超出实际 Scenario: {invalid_sessions}",
        )
    mismatched_session_ids = tuple(
        (index, scenario.sessions[index].id)
        for index in condition.observation_sessions
        if scenario.sessions[index].id != f"session-{index}"
    )
    if mismatched_session_ids:
        raise PreregistrationBindingError(
            condition.condition_id,
            f"观察 Session 索引与实际 session.id 不一致: {mismatched_session_ids}",
        )


def _verify_shared_grant_structures(
    registration: T16Preregistration,
    scenarios: dict[str, Scenario],
) -> None:
    signatures: dict[str, tuple[str, ...]] = {}
    owners: dict[str, str] = {}
    for condition in registration.conditions:
        structure_id = condition.capability.authorization_structure_id
        signature = tuple(
            sorted(
                item.model_dump_json()
                for item in _scenario_grants(scenarios[condition.condition_id])
            )
        )
        expected = signatures.setdefault(structure_id, signature)
        owners.setdefault(structure_id, condition.condition_id)
        if signature != expected:
            raise PreregistrationBindingError(
                condition.condition_id,
                f"实际 Authorization Grant 与同名结构 ID 不一致（基准条件 {owners[structure_id]}）",
            )


def _verify_pair_harnesses(
    registration: T16Preregistration,
    scenarios: dict[str, Scenario],
) -> None:
    signatures: dict[str, str] = {}
    owners: dict[str, str] = {}
    for condition in registration.conditions:
        signature = scenarios[condition.condition_id].harness.model_dump_json()
        expected = signatures.setdefault(condition.pair_group_id, signature)
        owners.setdefault(condition.pair_group_id, condition.condition_id)
        if signature != expected:
            raise PreregistrationBindingError(
                condition.condition_id,
                "能力匹配组的实际 Harness flags 不一致"
                f"（基准条件 {owners[condition.pair_group_id]}）",
            )


def _verify_pair_effect_selectors(
    registration: T16Preregistration,
    scenarios: dict[str, Scenario],
) -> None:
    signatures: dict[str, tuple[str, ...]] = {}
    owners: dict[str, str] = {}
    for condition in registration.conditions:
        signature = tuple(
            item.model_dump_json() for item in scenarios[condition.condition_id].effect_selectors
        )
        expected = signatures.setdefault(condition.pair_group_id, signature)
        owners.setdefault(condition.pair_group_id, condition.condition_id)
        if signature != expected:
            raise PreregistrationBindingError(
                condition.condition_id,
                "能力匹配组的实际 Effect selectors 不一致"
                f"（基准条件 {owners[condition.pair_group_id]}）",
            )


def _verify_pair_session_indices(
    registration: T16Preregistration,
    scenarios: dict[str, Scenario],
) -> None:
    signatures: dict[str, tuple[str, ...]] = {}
    owners: dict[str, str] = {}
    for condition in registration.conditions:
        signature = tuple(item.id for item in scenarios[condition.condition_id].sessions)
        expected = signatures.setdefault(condition.pair_group_id, signature)
        owners.setdefault(condition.pair_group_id, condition.condition_id)
        if signature != expected:
            raise PreregistrationBindingError(
                condition.condition_id,
                "能力匹配组的实际 Session 索引结构不一致"
                f"（基准条件 {owners[condition.pair_group_id]}）",
            )


def _scenario_grants(scenario: Scenario) -> tuple[AuthorizationGrant, ...]:
    step_grants = tuple(
        step.grant
        for session in scenario.sessions
        for step in session.steps
        if step.grant is not None
    )
    return (*scenario.grants, *step_grants)


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
