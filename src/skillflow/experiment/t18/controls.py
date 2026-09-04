"""四格内容合同机械绑定；只有两个实验因素可以不同。"""

from typing import Literal

from pydantic import TypeAdapter

from skillflow.experiment.t17.minimal.contracts import Sha256
from skillflow.experiment.t17.v2.configuration import canonical_digest
from skillflow.experiment.t18.catalog_models import LocalCatalog, LocalSkill
from skillflow.experiment.t18.matrix import FACTORS, CoreCell, LocalMatrix, ModeCell
from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.enums import EnforcementMode
from skillflow.models.scenario import Scenario
from skillflow.models.tool_calls import ToolArguments


class CellContract(StrictModel):
    """每个四格成员的内容、共享控制和完整执行身份。"""

    schema_version: Literal["18.0"] = "18.0"
    design_id: NonEmptyStr
    cell: ModeCell
    trial_id: NonEmptyStr
    shared_contract_sha256: Sha256
    skill_content_sha256: Sha256
    run_contract_sha256: Sha256


def configured_scenario(skill: LocalSkill, cell: CoreCell) -> Scenario:
    """只显式改变桥梁和执行模式；不得重写 Grant 或策略来源。"""
    mode = EnforcementMode.ENFORCE if cell.mode == "universal_enforce" else EnforcementMode.MONITOR
    scenario = skill.scenario.model_copy(
        update={
            "harness": skill.scenario.harness.model_copy(
                update={"shared_context": cell.bridge_enabled}
            ),
            "execution": skill.scenario.execution.model_copy(update={"mode": mode}),
        }
    )
    return Scenario.model_validate(scenario.model_dump())


def shared_digest(skill: LocalSkill, cell: CoreCell, domain: str) -> str:
    """整个场景只移除内容标记及桥梁轴；其余字段都进入同一合同。"""
    scenario = configured_scenario(skill, cell).model_dump(mode="json")
    scenario["assets"] = [
        a.model_dump(mode="json", exclude={"marker"}) for a in skill.scenario.assets
    ]
    scenario["harness"].pop("shared_context")
    direct_targets = {c.target.alias for c in skill.scenario.counterfactuals}
    source_actors = {
        step.skill
        for session in skill.scenario.sessions
        for step in session.steps
        if direct_targets.intersection(a.alias for a in step.outputs)
    }
    source_keys = {s.implementation.root for s in skill.scenario.skills if s.id in source_actors}
    programs = skill.bundle.model_dump(mode="json")["scripts"]
    for key in source_keys:
        programs[key].pop("output")
    return canonical_digest(
        {
            "scenario_structure": scenario,
            "task": skill.task_contract.model_dump(mode="json"),
            "plan": skill.task_plan.model_dump(mode="json"),
            "manifests": {k: v.model_dump(mode="json") for k, v in skill.manifests.items()},
            "tool_registry": TypeAdapter(ToolArguments).json_schema(),
            "structural_decisions": skill.bundle.decisions,
            "non_target_program": programs,
            "input_output_contract": {
                k: {"mime_type": v.output_mime_type, "actions": [a.action_id for a in v.actions]}
                for k, v in skill.bundle.scripts.items()
            },
            "mode": cell.mode,
            "model": "none-scripted" if domain == "scripted" else "V2FakeClient-all",
            "harness": "t18-reference-v1",
            "domain": domain,
            "seed": cell.seed,
            "semantic_instance": cell.semantic_instance,
            "repeat": cell.repeat,
        }
    )


def bind_matrix_controls(matrix: LocalMatrix, catalog: LocalCatalog) -> tuple[CellContract, ...]:
    """复用以完整控制相等为前提；不使用场景代号代替匹配。"""
    cells = {c.trial_id: c for c in matrix.cores}
    skills = {s.skill_variant_id: s for s in catalog.skills}
    result = []
    for group in matrix.hiaa_groups:
        group_hashes = set()
        for label, _, _ in FACTORS:
            cell = cells[group.cells[label]]
            skill = skills[cell.skill_variant_id]
            shared = shared_digest(skill, cell, matrix.domain)
            group_hashes.add(shared)
            result.append(
                CellContract(
                    design_id=group.design_id,
                    cell=label,
                    trial_id=cell.trial_id,
                    shared_contract_sha256=shared,
                    skill_content_sha256=canonical_digest(
                        {
                            "bundle": skill.bundle.model_dump(mode="json"),
                            "assets": [a.model_dump(mode="json") for a in skill.scenario.assets],
                        }
                    ),
                    run_contract_sha256=canonical_digest(
                        {
                            "shared": shared,
                            "cell": cell.model_dump(mode="json"),
                            "skill": skill.model_dump(mode="json"),
                        }
                    ),
                )
            )
        if len(group_hashes) != 1:
            raise ValueError("t18_hiaa_shared_contract_mismatch:" + group.design_id)
    return tuple(result)
