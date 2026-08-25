"""Scenario Session 与步骤的内部执行器。"""

from dataclasses import dataclass
from typing import assert_never

from skillflow.adapters.base import (
    HarnessSession,
    SkillBinding,
    SkillInvocation,
    SkillInvocationResult,
)
from skillflow.adapters.mock_harness import BenchmarkController, MockHarnessAdapter
from skillflow.benchmark.oracle_bridge import (
    OracleInvocationBinding,
    project_oracle_invocation,
)
from skillflow.instrumentation.errors import UnsupportedStepError
from skillflow.instrumentation.tool_receipt import ToolReceipt
from skillflow.models.provenance import Artifact
from skillflow.models.scenario import Scenario
from skillflow.models.scenario_parts import ScenarioStep, StepAction
from skillflow.oracle.sidecar import OracleSidecar


@dataclass(frozen=True, slots=True)
class ScenarioExecutionResult:
    """Runner 收尾阶段所需的运行事实。"""

    output_artifacts: tuple[Artifact, ...]
    receipts: tuple[ToolReceipt, ...]
    artifact_aliases: dict[str, tuple[str, ...]]


@dataclass(frozen=True, slots=True)
class _StepExecution:
    step: ScenarioStep
    harness: MockHarnessAdapter
    controller: BenchmarkController
    input_artifact_ids: tuple[str, ...]


def execute_scenario_sessions(
    scenario: Scenario,
    harness: MockHarnessAdapter,
    oracle: OracleSidecar,
) -> ScenarioExecutionResult:
    """按声明顺序执行全部 Session，并保持原有异常清理语义。"""
    outputs: list[Artifact] = []
    receipts: list[ToolReceipt] = []
    artifact_aliases: dict[str, tuple[str, ...]] = {}
    alias_artifacts: dict[str, str] = {}
    controller = BenchmarkController(harness)
    bindings = {
        skill.id: SkillBinding(skill.id, skill.implementation) for skill in scenario.skills
    }
    for session in scenario.sessions:
        harness.start_session(HarnessSession(session.id))
        try:
            invoked_skills = tuple(
                dict.fromkeys(
                    step.skill
                    for step in session.steps
                    if step.action is StepAction.INVOKE_SKILL and step.skill is not None
                )
            )
            for skill_id in invoked_skills:
                harness.load_skill(bindings[skill_id])
            for step in session.steps:
                input_ids = tuple(alias_artifacts[item.alias] for item in step.inputs)
                result = _execute_step(_StepExecution(step, harness, controller, input_ids))
                if step.action is StepAction.USER_CONFIRM and step.grant is not None:
                    oracle.record_grant(step.grant)
                if result is not None:
                    outputs.append(result.output)
                    receipts.extend(result.receipts)
                    aliases = tuple(output.root for output in step.outputs)
                    artifact_aliases[result.output.artifact_id] = aliases
                    alias_artifacts.update(
                        (output.alias, result.output.artifact_id) for output in step.outputs
                    )
                    oracle.record_invocation(
                        project_oracle_invocation(
                            OracleInvocationBinding(
                                step=step,
                                session_id=session.id,
                                result=result,
                            )
                        )
                    )
        finally:
            harness.end_session()
    return ScenarioExecutionResult(tuple(outputs), tuple(receipts), artifact_aliases)


def _execute_step(execution: _StepExecution) -> SkillInvocationResult | None:
    step = execution.step
    match step.action:
        case StepAction.INVOKE_SKILL:
            if step.skill is None:
                raise UnsupportedStepError(step.id, "invoke_skill without skill")
            return execution.harness.invoke_skill(
                SkillInvocation(step.skill, execution.input_artifact_ids)
            )
        case StepAction.REVOKE_SKILL:
            if step.skill is None or step.actor is None:
                raise UnsupportedStepError(step.id, "invalid revoke_skill")
            execution.controller.revoke_skill(step.skill, step.actor)
            return None
        case StepAction.UNLOAD_SKILL:
            if step.skill is None or step.actor is None:
                raise UnsupportedStepError(step.id, "invalid unload_skill")
            execution.controller.unload_skill(step.skill, step.actor)
            return None
        case StepAction.USER_CONFIRM:
            if step.actor is None or step.grant is None:
                raise UnsupportedStepError(step.id, "invalid user_confirm")
            execution.controller.confirm_tool(step.grant, step.actor)
            return None
        case (
            StepAction.WRITE_MEMORY
            | StepAction.READ_MEMORY
            | StepAction.REQUEST_TOOL
            | StepAction.RESTART_RUNTIME
        ):
            raise UnsupportedStepError(step.id, step.action.value)
        case _ as unreachable:
            assert_never(unreachable)
