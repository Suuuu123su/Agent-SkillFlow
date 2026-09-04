"""把历史设计输入转成独立第二版目录；不读取任何旧模型结果。"""

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING

from skillflow.benchmark.t12_fixtures import t12_fixture_registry
from skillflow.experiment.t17.live_matrix import load_live_preregistration
from skillflow.experiment.t17.minimal.artifacts import write_checked_json
from skillflow.experiment.t17.minimal.configuration import build_minimal_configuration
from skillflow.experiment.t17.minimal.contracts import NormalTaskContract
from skillflow.experiment.t17.reference_backend import ReferenceModelDecision
from skillflow.experiment.t17.v2.canonical import canonical_digest
from skillflow.experiment.t17.v2.catalog_models import (
    CatalogCondition,
    SkillBundle,
    SkillCatalog,
    SkillVariant,
)
from skillflow.experiment.t17.v2.claim_setup import claim_specs
from skillflow.experiment.t17.v2.config_models import V2Configuration
from skillflow.experiment.t17.v2.frozen import file_digest, inside
from skillflow.experiment.t17.v2.paired_setup import session_pairs
from skillflow.models.manifest import SkillManifest
from skillflow.models.matrix import ExperimentMatrix
from skillflow.models.scenario import Scenario
from skillflow.validation import validate_yaml_document

__all__ = [
    "build_configuration",
    "canonical_digest",
    "entry_fingerprints",
    "normal_contract_id",
    "write_configuration",
]

if TYPE_CHECKING:
    from skillflow.experiment.t17.v2.claim_models import ClaimActionSpec


def normal_contract_id(task: NormalTaskContract) -> str:
    """任务身份只含功能性要求；场景名和攻击标签不参与。"""
    return "normal-task:" + canonical_digest((task.artifacts, task.effects, task.evaluator_version))


def entry_fingerprints(
    root: Path, task: NormalTaskContract, bundle: SkillBundle
) -> dict[str, object]:
    """由真实文件重新推导能力、工具和格式，不能相信目录自报指纹。"""
    scenario = validate_yaml_document(inside(root, task.scenario_path), Scenario)
    paths = tuple(skill.manifest.root for skill in scenario.skills)
    manifests = tuple(validate_yaml_document(inside(root, path), SkillManifest) for path in paths)
    permissions = tuple(
        permission
        for manifest in manifests
        for permission in (manifest.requested_permissions or manifest.declared_permissions)
    )
    script_keys = tuple(skill.implementation.root for skill in scenario.skills)
    if set(script_keys) != set(bundle.scripts):
        raise ValueError("v2_bundle_scenario_implementation_mismatch")
    return {
        "manifest_paths": paths,
        "manifest_sha256": canonical_digest(
            tuple(file_digest(inside(root, path)).sha256 for path in paths)
        ),
        "capability_fingerprint": canonical_digest(permissions),
        "tool_registry_fingerprint": canonical_digest(
            (tuple(bundle.scripts[key].actions for key in script_keys), bundle.decisions)
        ),
        "input_schema_fingerprint": canonical_digest(
            tuple(
                (step.skill, step.inputs, step.outputs, step.tool_outputs)
                for session in scenario.sessions
                for step in session.steps
            )
        ),
        "output_schema_fingerprint": canonical_digest(ReferenceModelDecision.model_json_schema()),
        "task_contract_id": normal_contract_id(task),
        "scope_requirements": permissions,
        "lifetime_requirements": tuple(sorted({grant.lifetime.value for grant in scenario.grants})),
    }


def build_configuration(
    root: Path, destination: Path
) -> tuple[V2Configuration, dict[str, SkillBundle]]:
    """继承 24 条件和普通任务 v2，技能数据独立写入新目录。"""
    relative = destination.resolve().relative_to(root.resolve()).as_posix()
    base = validate_yaml_document(root / "scenarios/matrix/mvp.yaml", ExperimentMatrix)
    old = load_live_preregistration(root / "experiments/t17/preregistration.yaml")
    all_tasks = build_minimal_configuration(root).tasks
    tasks = tuple(
        task for task in all_tasks if task.scenario_path in {v.scenario.root for v in base.variants}
    )
    scripts, decisions = t12_fixture_registry()
    by_path = {task.scenario_path: "t17-v2-" + task.scenario_id.lower() for task in tasks}
    neutral_paths = {item.neutral_scenario.root for item in base.hiaa_designs}
    pairs = {item.target_scenario.root: item.neutral_scenario.root for item in base.hiaa_designs}
    bundles: dict[str, SkillBundle] = {}
    claims: dict[str, tuple[ClaimActionSpec, ...]] = {}
    entries = []
    for task in tasks:
        scenario = validate_yaml_document(root / task.scenario_path, Scenario)
        identifier = by_path[task.scenario_path]
        chosen = {
            skill.implementation.root: scripts[skill.implementation.root]
            for skill in scenario.skills
        }
        keys = {a.decision_key for s in chosen.values() for a in s.actions} | {
            a.input_gate.mismatch_decision_key
            for s in chosen.values()
            for a in s.actions
            if a.input_gate is not None
        }
        bundle = SkillBundle(
            bundle_id=identifier,
            scripts=chosen,
            decisions={key: decisions[key] for key in sorted(keys)},
        )
        source = relative + "/skills/" + identifier + ".json"
        bundles[source] = bundle
        claims[identifier] = claim_specs(scenario, bundle)
        role = (
            "neutral"
            if task.scenario_path in neutral_paths
            else ("benign-control" if task.benign_control else "attack")
        )
        target = pairs.get(task.scenario_path)
        pairing = scenario.pairing
        entries.append(
            SkillVariant.model_validate(
                {
                    "skill_variant_id": identifier,
                    "skill_family": scenario.task.id,
                    "attack_family": "control" if pairing is None else pairing.factor.value,
                    "variant_role": role,
                    "skill_version": "1.0",
                    "source_path": source,
                    "scenario_path": task.scenario_path,
                    "scenario_sha256": task.scenario_sha256,
                    "skill_content_sha256": hashlib.sha256(
                        (bundle.model_dump_json(indent=2, by_alias=True) + "\n").encode()
                    ).hexdigest(),
                    "neutral_pair_skill_id": None if target is None else by_path[target],
                    "pair_id": None if pairing is None else pairing.pair_id,
                    "risk_effect_selector": task.risk_selectors,
                    "harness_factor": (
                        "shared_context",
                        "persistent_memory",
                        "provenance_mode",
                        "enforcement_mode",
                    ),
                    "split": "validation",
                    **entry_fingerprints(root, task, bundle),
                }
            )
        )
    catalog = SkillCatalog(
        catalog_id="t17-v2-catalog",
        variants=tuple(entries),
        conditions=tuple(
            CatalogCondition(skill_variant_id=by_path[item.scenario.root], configuration=item)
            for item in base.variants
        ),
    )
    return V2Configuration(
        catalog=catalog,
        tasks=tasks,
        templates=old.semantic_templates,
        model1=old.model1_provider,
        model2=old.model2_provider,
        hiaa_designs=base.hiaa_designs,
        claim_bindings=claims,
        session_pairs=session_pairs(catalog, tasks),
    ), bundles


def write_configuration(
    root: Path, destination: Path, configuration: V2Configuration, bundles: dict[str, SkillBundle]
) -> None:
    """生成静态 JSON，拒绝覆盖任何已存在的版本目录。"""
    destination = inside(root, destination.resolve().relative_to(root.resolve()).as_posix())
    if any(not inside(root, path).is_relative_to(destination) for path in bundles):
        raise ValueError("v2_bundle_destination_escape")
    destination.mkdir(parents=True, exist_ok=False)
    for reference, bundle in bundles.items():
        path = inside(root, reference)
        path.parent.mkdir(parents=True, exist_ok=True)
        write_checked_json(path, bundle)
    write_checked_json(destination / "preregistration.json", configuration)
    write_checked_json(destination / "skill-catalog.json", configuration.catalog)
