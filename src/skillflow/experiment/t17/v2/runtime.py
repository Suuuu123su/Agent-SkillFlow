"""缺失输入可终态化的第二版执行器，旧路径仍保持严格模式。"""

from dataclasses import dataclass, field, replace

from skillflow.adapters.live_reference_harness import LiveReferenceHarnessAdapter
from skillflow.adapters.mock_harness import MockHarnessAdapter
from skillflow.benchmark.execution_policy import ScenarioExecutionPolicy
from skillflow.benchmark.harness_factory import HarnessFactorySetup, create_harness_with_backend
from skillflow.benchmark.replay_models import ReplaySourceState
from skillflow.benchmark.scenario_execution import (
    ScenarioCursor,
    ScenarioExecutor,
    ScenarioExecutorSetup,
)
from skillflow.benchmark.scripted_backend import ScriptedBackend
from skillflow.experiment.t17.reference_backend import ReferenceModelClient, ReferenceRunContext
from skillflow.experiment.t17.v2.backend import V2ReferenceBackend
from skillflow.experiment.t17.v2.runtime_models import ExecutionIssue, RunCapture
from skillflow.instrumentation.errors import UnsupportedStepError
from skillflow.models.scenario_parts import ScenarioStep, StepAction


class V2ScenarioExecutor(ScenarioExecutor):
    """不执行依赖缺失输入的步骤，其余会话继续并正常结束。"""

    def __init__(self, setup: ScenarioExecutorSetup, capture: RunCapture) -> None:
        """绑定受信运行身份与不含正文的失败记录。"""
        super().__init__(setup)
        self._capture = capture

    def _execute_and_record(self, step: ScenarioStep, session_id: str) -> None:
        self._capture.step_id = step.id
        self._capture.session_id = session_id
        try:
            self._input_ids(step)
        except UnsupportedStepError as error:
            if step.action is not StepAction.INVOKE_SKILL or not error.action.startswith(
                "required input missing:"
            ):
                raise
            self._capture.issues.append(
                ExecutionIssue(
                    run_id=self._capture.run_id,
                    session_id=session_id,
                    step_id=step.id,
                    reason="missing_input",
                    references=tuple(i.alias for i in step.inputs if i.alias not in self._aliases),
                )
            )
            if self._oracle is not None and step.skill is not None:
                self._oracle.record_unexecuted_step(step.id, session_id, step.skill)
            return
        super()._execute_and_record(step, session_id)
        if self._capture.capture_checkpoints:
            produced = {item.alias for item in step.outputs} | {
                item.alias.alias for item in step.tool_outputs
            }
            for target in self._scenario.counterfactuals:
                alias = target.target.alias
                if alias in produced and alias in self._aliases:
                    snapshot = self.snapshot()
                    cursor = ScenarioCursor(
                        snapshot.cursor.session_index,
                        snapshot.cursor.step_index + 1,
                        session_active=True,
                    )
                    self._capture.checkpoints[alias] = ReplaySourceState(
                        self._harness.checkpoint(),
                        replace(snapshot, cursor=cursor),
                        self._aliases[alias],
                    )


@dataclass(slots=True)
class V2HarnessFactory:
    """完整保留可信存储、策略、工具与检查点，只允许模型选择动作。"""

    client: ReferenceModelClient | None
    task_prompt: str | None = None
    capture_checkpoints: bool = True
    captures: dict[str, RunCapture] = field(default_factory=dict)
    _bindings: dict[int, RunCapture] = field(default_factory=dict)

    @property
    def execution_policy(self) -> ScenarioExecutionPolicy:
        """只对显式采用新版的运行取消旧固定路径成功断言。"""
        return ScenarioExecutionPolicy(self.executor, validate_scripted_expectations=False)

    def executor(self, setup: ScenarioExecutorSetup) -> ScenarioExecutor:
        """从实际 Harness 身份绑定执行器，而非推测 Run ID。"""
        return V2ScenarioExecutor(setup, self._bindings[id(setup.harness)])

    def __call__(self, setup: HarnessFactorySetup) -> MockHarnessAdapter:
        """每个 Run 都有独立记录，模型只接触正常任务内容。"""
        capture = RunCapture(setup.run_id, capture_checkpoints=self.capture_checkpoints)
        self.captures[setup.run_id] = capture
        backend = (
            ScriptedBackend(setup.scripts)
            if self.client is None
            else V2ReferenceBackend(
                setup.scripts,
                self.client,
                ReferenceRunContext(
                    setup.scenario.id, self.task_prompt or setup.scenario.task.prompt
                ),
                capture,
                setup.event_store,
            )
        )
        harness = create_harness_with_backend(setup, backend, LiveReferenceHarnessAdapter)
        self._bindings[id(harness)] = capture
        return harness
