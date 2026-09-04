"""逐单元执行与故障终态；尝试中断后仍逐条列明未运行的调度。"""

from dataclasses import dataclass
from typing import TypeVar

from skillflow.analysis.errors import AnalysisInvariantError
from skillflow.experiment.t16.budget import BudgetExceededError
from skillflow.experiment.t17.observation_models import ObservationBindingError
from skillflow.experiment.t17.v2.api_models import AccountingClient, V2BudgetExhaustedError
from skillflow.experiment.t17.v2.config_models import V2Trial
from skillflow.experiment.t17.v2.replay_execution import execute_replay
from skillflow.experiment.t17.v2.run_models import (
    CoreTerminal,
    ReplayTerminal,
    TerminalStatus,
    UnitUsage,
)
from skillflow.experiment.t17.v2.stage_contract import unit_identity
from skillflow.experiment.t17.v2.unit_execution import (
    CoreExecution,
    ExecutionContext,
    compact_id,
    execute_core,
    file_inventory,
)

TerminalT = TypeVar("TerminalT", CoreTerminal, ReplayTerminal)


@dataclass(slots=True)
class UnitScheduler:
    """调度状态只含受信上下文、预算接口和停止标志。"""

    context: ExecutionContext
    accounting: AccountingClient | None
    stopped: bool = False
    startup_failure: tuple[TerminalStatus, str] | None = None

    def run_core(self, trial: V2Trial) -> tuple[CoreTerminal, CoreExecution | None]:
        """依赖缺失由运行时处理，框架故障才进入本层分类。"""
        context = self.context
        identity = unit_identity(context.phase, context.matrix, trial, trial.trial_id)
        if self.startup_failure is not None:
            status, reason = self.startup_failure
            self.startup_failure, self.stopped = None, True
            return CoreTerminal(identity=identity, status=status, reason=reason), None
        if self.stopped:
            return CoreTerminal(identity=identity, status="not_run", reason="attempt_stopped"), None
        execution = None
        try:
            if self.accounting is not None:
                self.accounting.begin_unit(trial.trial_id)
            execution = execute_core(context, trial)
            terminal = execution.terminal
        except (Exception, KeyboardInterrupt) as error:  # noqa: BLE001 -- 停止但保存所有调度终态。
            status, reason = failure_category(error)
            terminal = CoreTerminal(
                identity=identity,
                status=status,
                reason=reason,
                raw_files=file_inventory(
                    context.output, context.output / "core" / compact_id(trial.trial_id)
                ),
            )
            self.stopped = status != "evidence_binding_failure"
        return self._with_usage(terminal), execution

    def run_replay(
        self, trial: V2Trial, core: CoreTerminal, execution: CoreExecution | None, alias: str
    ) -> ReplayTerminal:
        """每组重放共享对应核心任务；源任务不可用时不伪造对照。"""
        context = self.context
        unit_id = trial.replay_pair_ids[alias]
        identity = unit_identity(context.phase, context.matrix, trial, unit_id)
        if self.stopped or execution is None:
            return ReplayTerminal(
                identity=identity,
                source_core_run_id=core.run_id,
                target_alias=alias,
                status="not_run",
                reason="core_or_attempt_unavailable",
            )
        try:
            if self.accounting is not None:
                self.accounting.begin_unit(unit_id)
            terminal = execute_replay(context, trial, execution, alias)
        except (Exception, KeyboardInterrupt) as error:  # noqa: BLE001 -- 分支中断也留下终态。
            status, reason = failure_category(error)
            terminal = ReplayTerminal(
                identity=identity,
                source_core_run_id=core.run_id,
                target_alias=alias,
                status=status,
                reason=reason,
                raw_files=file_inventory(
                    context.output, context.output / "replay" / compact_id(unit_id)
                ),
            )
            self.stopped = status != "evidence_binding_failure"
        return self._with_usage(terminal)

    def _with_usage(self, terminal: TerminalT) -> TerminalT:
        usage = self.usage()
        if not usage.complete:
            self.stopped = True
            return terminal.model_copy(
                update={
                    "usage": usage,
                    "status": "infrastructure_invalid",
                    "reason": "usage_unavailable",
                }
            )
        return terminal.model_copy(update={"usage": usage})

    def usage(self) -> UnitUsage:
        """没有模型调用的本地验证明确使用零 API 用量。"""
        try:
            return UnitUsage() if self.accounting is None else self.accounting.unit_usage()
        except (Exception, KeyboardInterrupt) as error:  # noqa: BLE001 -- 未知用量不能冒充零费用。
            self.stopped = True
            return UnitUsage(complete=False, missing_reason=type(error).__name__)


def failure_category(error: BaseException) -> tuple[TerminalStatus, str]:
    """只返回封闭错误类别，不把可能含正文的异常 message 写入报告。"""
    if isinstance(error, (BudgetExceededError, V2BudgetExhaustedError)):
        return "budget_exhausted", type(error).__name__
    if isinstance(error, (ObservationBindingError, AnalysisInvariantError)):
        return "evidence_binding_failure", type(error).__name__
    if isinstance(error, (OSError, KeyboardInterrupt)):
        return "infrastructure_invalid", type(error).__name__
    return "protocol_error", type(error).__name__
