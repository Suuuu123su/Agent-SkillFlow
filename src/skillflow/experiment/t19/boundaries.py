"""来源输出不符合桥梁数据合同是可记录任务失败，不是基础设施成功。"""

from skillflow.benchmark.scenario_execution import ScenarioExecutorSetup
from skillflow.experiment.t17.v2.runtime import V2ScenarioExecutor
from skillflow.experiment.t17.v2.runtime_models import RunCapture
from skillflow.models.base import StrictModel
from skillflow.models.scenario_parts import ScenarioStep


class BoundaryIssue(StrictModel):
    """不能无损分离时保留源引用与未执行步骤，不伪造净化产物。"""

    run_id: str
    session_id: str
    step_id: str
    reason: str
    artifact_ids: tuple[str, ...]


class RxScenarioExecutor(V2ScenarioExecutor):
    """复用原会话推进与Oracle未执行步骤合同。"""

    def __init__(
        self, setup: ScenarioExecutorSetup, capture: RunCapture, issues: list[BoundaryIssue]
    ) -> None:
        """绑定本链的边界失败收集器。"""
        super().__init__(setup, capture)
        self.boundary_issues = issues

    def _execute_and_record(self, step: ScenarioStep, session_id: str) -> None:
        try:
            super()._execute_and_record(step, session_id)
        except (ValueError, TypeError) as error:
            if str(error) not in {
                "t19_bridge_control_not_losslessly_separable",
                "t19_neutralization_not_separable",
                "t19_neutralization_source_not_canonical",
            }:
                raise
            self.boundary_issues.append(
                BoundaryIssue(
                    run_id=self._capture.run_id,
                    session_id=session_id,
                    step_id=step.id,
                    reason=str(error),
                    artifact_ids=self._input_ids(step),
                )
            )
            if self._oracle is not None and step.skill is not None:
                self._oracle.record_unexecuted_step(step.id, session_id, step.skill)
