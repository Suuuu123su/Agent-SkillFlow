"""可选的内部步骤策略；旧入口仍要求完整确定性脚本路径。"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeAlias

from skillflow.benchmark.scenario_execution import ScenarioExecutor, ScenarioExecutorSetup

ScenarioExecutorFactory: TypeAlias = Callable[[ScenarioExecutorSetup], ScenarioExecutor]


@dataclass(frozen=True, slots=True)
class ScenarioExecutionPolicy:
    """只替换内部步骤编排，不修改公开 Harness 协议。"""

    factory: ScenarioExecutorFactory = ScenarioExecutor
    validate_scripted_expectations: bool = True
