"""Scenario Session 与步骤的可恢复内部执行器。"""

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
class ScenarioCursor:
    """下一个待执行步骤及当前 Session 是否仍活动。"""

    session_index: int
    step_index: int
    session_active: bool


@dataclass(frozen=True, slots=True)
class ScenarioExecutionSnapshot:
    """与 Harness checkpoint 同点冻结的编排器状态。"""

    cursor: ScenarioCursor
    output_artifacts: tuple[Artifact, ...]
    receipts: tuple[ToolReceipt, ...]
    alias_artifacts: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class ScenarioExecutionResult:
    """Runner 收尾阶段所需的运行事实。"""

    output_artifacts: tuple[Artifact, ...]
    receipts: tuple[ToolReceipt, ...]
    artifact_aliases: dict[str, tuple[str, ...]]


@dataclass(frozen=True, slots=True)
class ScenarioExecutorSetup:
    """新运行或恢复运行所需的固定依赖。"""

    scenario: Scenario
    harness: MockHarnessAdapter
    oracle: OracleSidecar | None = None
    snapshot: ScenarioExecutionSnapshot | None = None


@dataclass(frozen=True, slots=True)
class _StepExecution:
    step: ScenarioStep
    harness: MockHarnessAdapter
    controller: BenchmarkController
    input_artifact_ids: tuple[str, ...]


class ScenarioExecutor:
    """可在 Artifact 输出 step 边界暂停并从快照继续。"""

    def __init__(self, setup: ScenarioExecutorSetup) -> None:
        """复制快照容器，所有外部依赖保持显式注入。"""
        self._scenario = setup.scenario
        self._harness = setup.harness
        self._oracle = setup.oracle
        self._controller = BenchmarkController(setup.harness)
        self._bindings = {
            skill.id: SkillBinding(skill.id, skill.implementation)
            for skill in setup.scenario.skills
        }
        snapshot = setup.snapshot
        self._cursor = (
            ScenarioCursor(session_index=0, step_index=0, session_active=False)
            if snapshot is None
            else snapshot.cursor
        )
        self._outputs = [] if snapshot is None else list(snapshot.output_artifacts)
        self._receipts = [] if snapshot is None else list(snapshot.receipts)
        self._aliases = {} if snapshot is None else dict(snapshot.alias_artifacts)

    def run_all(self) -> ScenarioExecutionResult:
        """执行全部剩余步骤并结束所有 Session。"""
        self._advance(None)
        return self.result()

    def run_until_alias(self, alias: str) -> ScenarioExecutionSnapshot:
        """执行到目标 alias 产生后暂停，保留当前 Session。"""
        if alias in self._aliases:
            raise UnsupportedStepError(alias, "target alias already produced")
        self._advance(alias)
        if alias not in self._aliases:
            raise UnsupportedStepError(alias, "target alias was not produced")
        return self.snapshot()

    def replace_alias(self, alias: str, artifact_id: str) -> None:
        """只替换一个已存在 alias 的活动 Artifact 版本。"""
        if alias not in self._aliases:
            raise UnsupportedStepError(alias, "cannot replace unknown alias")
        self._aliases[alias] = artifact_id

    def snapshot(self) -> ScenarioExecutionSnapshot:
        """冻结当前游标、输出、Receipt 与 alias 绑定。"""
        return ScenarioExecutionSnapshot(
            cursor=self._cursor,
            output_artifacts=tuple(self._outputs),
            receipts=tuple(self._receipts),
            alias_artifacts=tuple(self._aliases.items()),
        )

    def result(self) -> ScenarioExecutionResult:
        """投影为 ScenarioRunner 的兼容结果。"""
        aliases: dict[str, list[str]] = {}
        for alias, artifact_id in self._aliases.items():
            aliases.setdefault(artifact_id, []).append(f"artifact:{alias}")
        return ScenarioExecutionResult(
            output_artifacts=tuple(self._outputs),
            receipts=tuple(self._receipts),
            artifact_aliases={key: tuple(value) for key, value in aliases.items()},
        )

    def artifact_id(self, alias: str) -> str:
        """读取一个已产生 alias 的当前 Artifact ID。"""
        try:
            return self._aliases[alias]
        except KeyError as error:
            raise UnsupportedStepError(alias, "unknown artifact alias") from error

    def _advance(self, stop_alias: str | None) -> None:
        while self._cursor.session_index < len(self._scenario.sessions):
            session = self._scenario.sessions[self._cursor.session_index]
            if not self._cursor.session_active:
                self._start_session()
            while self._cursor.step_index < len(session.steps):
                step = session.steps[self._cursor.step_index]
                self._execute_and_record(step, session.id)
                self._cursor = ScenarioCursor(
                    session_index=self._cursor.session_index,
                    step_index=self._cursor.step_index + 1,
                    session_active=True,
                )
                if stop_alias is not None and stop_alias in self._aliases:
                    return
            self._harness.end_session()
            self._cursor = ScenarioCursor(
                session_index=self._cursor.session_index + 1,
                step_index=0,
                session_active=False,
            )

    def _start_session(self) -> None:
        session = self._scenario.sessions[self._cursor.session_index]
        self._harness.start_session(HarnessSession(session.id))
        invoked_skills = tuple(
            dict.fromkeys(
                step.skill
                for step in session.steps
                if step.action is StepAction.INVOKE_SKILL and step.skill is not None
            )
        )
        for skill_id in invoked_skills:
            self._harness.load_skill(self._bindings[skill_id])
        self._cursor = ScenarioCursor(
            session_index=self._cursor.session_index,
            step_index=0,
            session_active=True,
        )

    def _execute_and_record(self, step: ScenarioStep, session_id: str) -> None:
        inputs = tuple(self._aliases[item.alias] for item in step.inputs)
        result = _execute_step(_StepExecution(step, self._harness, self._controller, inputs))
        if (
            step.action is StepAction.USER_CONFIRM
            and step.grant is not None
            and self._oracle is not None
        ):
            self._oracle.record_grant(step.grant)
        if result is None:
            return
        self._outputs.append(result.output)
        self._receipts.extend(result.receipts)
        self._aliases.update((output.alias, result.output.artifact_id) for output in step.outputs)
        if self._oracle is not None:
            self._oracle.record_invocation(
                project_oracle_invocation(
                    OracleInvocationBinding(step=step, session_id=session_id, result=result)
                )
            )


def execute_scenario_sessions(
    scenario: Scenario,
    harness: MockHarnessAdapter,
    oracle: OracleSidecar,
) -> ScenarioExecutionResult:
    """兼容 ScenarioRunner 的一次性执行入口。"""
    return ScenarioExecutor(ScenarioExecutorSetup(scenario, harness, oracle)).run_all()


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
