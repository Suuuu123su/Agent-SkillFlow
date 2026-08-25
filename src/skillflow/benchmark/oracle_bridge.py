"""ScenarioRunner 与独立 Oracle 之间的单向证据桥。"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from skillflow.adapters.base import SkillInvocationResult
from skillflow.benchmark.manifests import load_oracle_manifests
from skillflow.benchmark.scripted_backend import FixtureScript
from skillflow.instrumentation.errors import FixtureNotFoundError, UnsupportedStepError
from skillflow.instrumentation.tool_receipt import ToolReceipt
from skillflow.models.scenario import Scenario
from skillflow.models.scenario_parts import ScenarioStep
from skillflow.oracle.models import (
    OracleActionPlan,
    OracleAttemptEvidence,
    OracleInvocationEvidence,
    OracleReceiptEvidence,
    OracleRunPlan,
    OracleSkillPlan,
)
from skillflow.oracle.sidecar import OracleSidecar


@dataclass(frozen=True, slots=True)
class OracleSetup:
    """运行前构造 sidecar 所需的受控声明输入。"""

    scenario_path: Path
    scenario: Scenario
    run_id: str
    scripts: Mapping[str, FixtureScript]


@dataclass(frozen=True, slots=True)
class OracleInvocationBinding:
    """Runner 在一次调用完成后提供的最小稳定 ID 绑定。"""

    step: ScenarioStep
    session_id: str
    result: SkillInvocationResult


def build_oracle_sidecar(setup: OracleSetup) -> OracleSidecar:
    """在 Harness 启动前冻结 Manifest 与 Scripted 动作计划。"""
    skill_plans: list[OracleSkillPlan] = []
    for skill in setup.scenario.skills:
        try:
            script = setup.scripts[skill.implementation.root]
        except KeyError as error:
            raise FixtureNotFoundError(skill.implementation.root) from error
        skill_plans.append(
            OracleSkillPlan(
                skill_id=skill.id,
                actions=tuple(
                    OracleActionPlan(action.action_id, action.arguments)
                    for action in script.actions
                ),
            )
        )
    return OracleSidecar(
        OracleRunPlan(
            run_id=setup.run_id,
            scenario=setup.scenario,
            skills=tuple(skill_plans),
            manifests=load_oracle_manifests(setup.scenario_path, setup.scenario),
        )
    )


def project_oracle_invocation(binding: OracleInvocationBinding) -> OracleInvocationEvidence:
    """只投影 ID/Receipt，不把 Artifact observed_label 交给 Oracle。"""
    skill_id = binding.step.skill
    if skill_id is None:
        raise UnsupportedStepError(binding.step.id, "invoke_skill without skill")
    result = binding.result
    return OracleInvocationEvidence(
        step_id=binding.step.id,
        skill_id=skill_id,
        session_id=binding.session_id,
        call_id=result.call_id,
        input_artifact_ids=result.input_artifact_ids,
        output_artifact_id=result.output.artifact_id,
        output_aliases=tuple(output.root for output in binding.step.outputs),
        attempts=tuple(
            OracleAttemptEvidence(
                action_id=attempt.action_id,
                actor_id=attempt.actor_id,
                call_id=attempt.call_id,
                tool=attempt.tool,
                arguments=attempt.arguments,
                argument_artifact_id=attempt.argument_artifact_id,
                executed=attempt.executed,
            )
            for attempt in result.attempts
        ),
        skipped_action_ids=result.skipped_action_ids,
        receipts=tuple(_project_receipt(receipt, binding.step) for receipt in result.receipts),
    )


def _project_receipt(
    receipt: ToolReceipt,
    step: ScenarioStep,
) -> OracleReceiptEvidence:
    aliases_by_index = {
        output.output_index: output.alias.root
        for output in step.tool_outputs
        if output.action_id == receipt.action_id
    }
    return OracleReceiptEvidence(
        action_id=receipt.action_id,
        receipt_id=receipt.receipt_id,
        effect_id=receipt.effect_id,
        actor_id=receipt.actor_id,
        call_id=receipt.call_id,
        timestamp=receipt.timestamp,
        tool=receipt.tool,
        argument_artifact_id=receipt.argument_artifact_id,
        receipt_artifact_id=receipt.receipt_artifact_id,
        output_artifact_ids=receipt.output_artifact_ids,
        output_aliases=tuple(
            ((alias,) if (alias := aliases_by_index.get(index)) is not None else ())
            for index in range(len(receipt.output_artifact_ids))
        ),
    )
