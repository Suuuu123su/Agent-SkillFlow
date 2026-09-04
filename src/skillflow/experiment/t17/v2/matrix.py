"""从技能目录机械展开任务，防御仅补齐不存在的模式。"""

import hashlib
from collections import defaultdict
from pathlib import Path

from skillflow.experiment.t17.live_matrix import T17LiveStage, defense_base_key
from skillflow.experiment.t17.v2.canonical import model_digest
from skillflow.experiment.t17.v2.catalog_models import CatalogCondition, SkillBundle, SkillCatalog
from skillflow.experiment.t17.v2.claim_setup import claim_specs
from skillflow.experiment.t17.v2.config_models import V2Configuration, V2Matrix, V2Trial
from skillflow.experiment.t17.v2.configuration import canonical_digest, entry_fingerprints
from skillflow.experiment.t17.v2.frozen import file_digest, inside
from skillflow.experiment.t17.v2.paired_setup import session_pairs
from skillflow.models.enums import EnforcementMode
from skillflow.models.scenario import Scenario
from skillflow.validation import validate_yaml_document


def verify_catalog_inputs(root: Path, config: V2Configuration) -> None:
    """每次运行前重读技能、清单和任务；目录里的哈希不是受信事实。"""
    SkillCatalog.model_validate(config.catalog.model_dump())
    if config.session_pairs != session_pairs(config.catalog, config.tasks):
        raise ValueError("v2_session_pair_design_drift")
    tasks = {task.scenario_path: task for task in config.tasks}
    for entry in config.catalog.variants:
        path = inside(root, entry.source_path)
        if file_digest(path).sha256 != entry.skill_content_sha256:
            raise ValueError("v2_skill_content_drift")
        if file_digest(inside(root, entry.scenario_path)).sha256 != entry.scenario_sha256:
            raise ValueError("v2_scenario_content_drift")
        task = tasks[entry.scenario_path]
        if (
            task.scenario_sha256 != entry.scenario_sha256
            or task.risk_selectors != entry.risk_effect_selector
        ):
            raise ValueError("v2_task_scenario_binding")
        bundle = SkillBundle.model_validate_json(path.read_text(encoding="utf-8"))
        scenario = validate_yaml_document(inside(root, entry.scenario_path), Scenario)
        if config.claim_bindings[entry.skill_variant_id] != claim_specs(scenario, bundle):
            raise ValueError("v2_claim_specification_drift")
        for name, value in entry_fingerprints(root, task, bundle).items():
            if getattr(entry, name) != value:
                raise ValueError("v2_catalog_input_fingerprint_drift:" + name)


def build_matrix(root: Path, config: V2Configuration, stage: T17LiveStage) -> V2Matrix:
    """先复核实际输入，再展开所有条件、表述和重复。"""
    verify_catalog_inputs(root, config)
    entries = {item.skill_variant_id: item for item in config.catalog.variants}
    tasks = {item.scenario_path: item for item in config.tasks}
    conditions = _conditions(config.catalog, stage)
    canary = stage in {T17LiveStage.CANARY, T17LiveStage.MODEL2_CANARY}
    templates = config.templates[:1] if canary else config.templates
    repeats = 1 if canary else config.repeats
    trials = []
    for condition, source in conditions:
        entry = entries[condition.skill_variant_id]
        variant = condition.configuration
        scenario = validate_yaml_document(inside(root, entry.scenario_path), Scenario)
        task = tasks[entry.scenario_path]
        for template in templates:
            for repeat in range(1, repeats + 1):
                identity = f"{variant.variant}-{template.template_id}-r{repeat}"
                trial_id = f"{config.protocol_id}-{stage.value}-{identity}"
                trials.append(
                    V2Trial(
                        trial_id=trial_id,
                        condition_id=variant.variant,
                        source_variant=source,
                        configuration=variant,
                        skill_variant_id=entry.skill_variant_id,
                        skill_content_sha256=entry.skill_content_sha256,
                        manifest_sha256=entry.manifest_sha256,
                        task_contract_id=entry.task_contract_id,
                        task_contract_sha256=model_digest(task),
                        semantic_instance_id=variant.variant + "-" + template.template_id,
                        semantic_template_id=template.template_id,
                        repeat_index=repeat,
                        task_prompt=template.prefix + scenario.task.prompt,
                        defense_base_id=hashlib.sha256(
                            defense_base_key(variant).encode()
                        ).hexdigest(),
                        enforcement_mode=variant.enforcement_mode,
                        replay_pair_ids={
                            pair.target.alias: trial_id + "--replay--" + pair.target.alias
                            for pair in scenario.counterfactuals
                        },
                    )
                )
    return V2Matrix(
        protocol_id=config.protocol_id,
        matrix_id=config.protocol_id + "-" + stage.value,
        stage=stage,
        configuration_sha256=model_digest(config),
        catalog_sha256=model_digest(config.catalog),
        provider=config.model2
        if stage in {T17LiveStage.MODEL2_CANARY, T17LiveStage.MODEL2}
        else config.model1,
        scheduled_core_trials=len(trials),
        scheduled_replay_pairs=sum(len(t.replay_pair_ids) for t in trials),
        trials=tuple(trials),
    )


def _conditions(
    catalog: SkillCatalog, stage: T17LiveStage
) -> tuple[tuple[CatalogCondition, str], ...]:
    if not catalog.conditions:
        raise ValueError("v2_catalog_conditions_required")
    if stage is not T17LiveStage.DEFENSE:
        return tuple((item, item.configuration.variant) for item in catalog.conditions)
    grouped: dict[str, list[CatalogCondition]] = defaultdict(list)
    for item in catalog.conditions:
        key = canonical_digest((item.skill_variant_id, defense_base_key(item.configuration)))
        grouped[key].append(item)
    result = []
    for values in grouped.values():
        modes = {item.configuration.enforcement_mode for item in values}
        if len(modes) != 1:
            continue
        source = values[0]
        mode = (
            EnforcementMode.ENFORCE if EnforcementMode.MONITOR in modes else EnforcementMode.MONITOR
        )
        variant = source.configuration.model_copy(
            update={
                "variant": source.configuration.variant + "-defense-" + mode.value,
                "enforcement_mode": mode,
            }
        )
        result.append(
            (
                CatalogCondition(skill_variant_id=source.skill_variant_id, configuration=variant),
                source.configuration.variant,
            )
        )
    return tuple(result)
