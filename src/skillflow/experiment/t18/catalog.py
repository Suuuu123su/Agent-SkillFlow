"""固定 8 类已有配对与 4 个正常对照；中性版本不增加任何权限。"""

import hashlib
from dataclasses import replace
from pathlib import Path

from skillflow.benchmark.manifests import load_manifests
from skillflow.benchmark.t12_fixtures import (
    CONSUMER_COMPLETE,
    CONTEXT_NEUTRAL,
    t12_fixture_registry,
)
from skillflow.defense.models import Mechanism
from skillflow.experiment.t17.minimal.contracts import (
    MinimalConfiguration,
    NormalArtifactRequirement,
    NormalTaskContract,
)
from skillflow.experiment.t17.v2.catalog_models import SkillBundle
from skillflow.experiment.t18.catalog_models import LocalCatalog, LocalSkill
from skillflow.experiment.t18.held_out import held_out_skills
from skillflow.experiment.t18.matrix import ATTACK_BASES, BENIGN_BASES, PAIRED_ROLES, Role
from skillflow.experiment.t18.planning import compile_task_plan
from skillflow.models.scenario import Scenario
from skillflow.validation import validate_yaml_document

LABELS: dict[str, tuple[Mechanism, ...]] = {
    "B1": ("privilege",),
    "S1": ("privilege",),
    "L1": ("privilege",),
    "C1": ("context-tool",),
    "C2": ("context-tool",),
    "M1": ("memory", "privilege"),
    "M2": ("memory", "privilege"),
    "A1": ("authorization", "privilege"),
}


def build_catalog(root: Path, *, include_held_out: bool = True) -> LocalCatalog:
    """先加载既有可信任务，不读取任何历史或新运行结果。"""
    minimal = validate_yaml_document(
        root / "experiments/t17/minimal-v1/preregistration.yaml", MinimalConfiguration
    )
    tasks = {task.scenario_id: task for task in minimal.tasks}
    skills: list[LocalSkill] = []
    for base in (*ATTACK_BASES, *BENIGN_BASES):
        task = tasks[base]
        source = root / task.scenario_path
        scenario = validate_yaml_document(source, Scenario)
        scenario = scenario.model_copy(
            update={
                "pairing": None,
                "canary": None,
                "expected_metrics": (),
                "expected_influences": (),
                "success_assertions": (),
            }
        )
        task = _functional_task(task, scenario)
        scripts, decisions = t12_fixture_registry()
        keys = {s.implementation.root for s in scenario.skills}
        scripts = {key: scripts[key] for key in keys}
        bundle = SkillBundle(
            bundle_id=base.lower() + "-attack", scripts=scripts, decisions=decisions
        )
        plan_scenario, plan_bundle = _plan_program(root, base, scenario, bundle)
        plan = compile_task_plan(plan_scenario, plan_bundle.scripts, task)
        manifests = {b.skill_id: b.manifest for b in load_manifests(source, scenario)}
        roles: tuple[Role, ...] = PAIRED_ROLES if base in ATTACK_BASES else ("benign-control",)
        for role in roles:
            variant, program = _variant(root, base, role, scenario, bundle)
            skills.append(
                LocalSkill(
                    skill_variant_id=base.lower() + "-" + role,
                    base_id=base,
                    role=role,
                    split="development" if base in ATTACK_BASES else "control",
                    scenario_path=task.scenario_path,
                    scenario=variant,
                    bundle=program,
                    manifests=manifests,
                    task_contract=task,
                    task_plan=plan,
                    scoring_labels=LABELS[base] if role == "attack" else (),
                    paired_skill_id=base.lower() + "-neutral" if role == "attack" else None,
                    adaptation_note="内容与动作选择可不同；任务、能力、工具类型和授权不因中性角色增权。",
                )
            )
    if include_held_out:
        skills.extend(held_out_skills(root, tuple(skills)))
    return LocalCatalog(skills=tuple(skills), held_out_included=include_held_out)


def _functional_task(task: NormalTaskContract, scenario: Scenario) -> NormalTaskContract:
    # A memory payload is input, not an exact-answer commitment shared by target/neutral.
    if task.scenario_id not in {"M1", "M2"}:
        return task.model_copy(
            update={"revision_rationale": "T18 配对共用原正常任务；内容版本与风险选择器独立。"}
        )
    aliases = ("task-result",) if task.scenario_id == "M1" else ("m2-result-1", "m2-result-3")
    sessions = {a.alias: s.id for s in scenario.sessions for step in s.steps for a in step.outputs}
    return task.model_copy(
        update={
            "artifacts": tuple(
                NormalArtifactRequirement(
                    alias=alias,
                    expected_sha256=hashlib.sha256(CONSUMER_COMPLETE).hexdigest(),
                    session_id=sessions[alias],
                )
                for alias in aliases
            ),
            "revision_rationale": (
                "T18 正常任务要求依赖实际记忆读取的最终处理结果；不将攻击载荷哈希当作正常答案。"
            ),
        }
    )


def _plan_program(
    root: Path, base: str, scenario: Scenario, bundle: SkillBundle
) -> tuple[Scenario, SkillBundle]:
    if base in {"S1", "L1"}:
        return _variant(root, base, "neutral", scenario, bundle)
    return scenario, bundle


def _variant(
    root: Path, base: str, role: Role, scenario: Scenario, bundle: SkillBundle
) -> tuple[Scenario, SkillBundle]:
    scripts = dict(bundle.scripts)
    variant = scenario
    if role == "neutral":
        if base == "C1":
            key = "fixture://t12/context-target"
            scripts[key] = replace(scripts[key], output=CONTEXT_NEUTRAL)
        elif base in {"C2", "M1", "M2"}:
            marker = '{"route":"log"}' if base == "C2" else "memory-neutral"
            variant = scenario.model_copy(
                update={
                    "assets": tuple(
                        a.model_copy(update={"marker": marker}) for a in scenario.assets
                    )
                }
            )
        elif base == "A1":
            key = "fixture://t12/claim-source"
            scripts[key] = replace(scripts[key], output=b"user-no-grant!")
        elif base == "B1":
            scripts = {key: replace(script, actions=()) for key, script in scripts.items()}
        elif base == "S1":
            registry, _ = t12_fixture_registry()
            scripts["fixture://t12/scope-adjacent"] = registry["fixture://t12/scope-allowed"]
        elif base == "L1":
            control = validate_yaml_document(
                root / "scenarios/benign/l1_session_control.yaml", Scenario
            )
            variant = scenario.model_copy(update={"sessions": control.sessions})
    return Scenario.model_validate(variant.model_dump()), SkillBundle(
        bundle_id=base.lower() + "-" + role,
        scripts=scripts,
        decisions=bundle.decisions,
    )
