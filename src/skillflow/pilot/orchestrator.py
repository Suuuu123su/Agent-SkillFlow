"""确保同一个 Scenario 交给两个 T15 Adapter。"""

from pathlib import Path
from typing import Protocol

from skillflow.pilot.comparison import compare_observations
from skillflow.pilot.models import PilotObservation, PilotScenarioComparison


class PilotHarnessAdapter(Protocol):
    """T15 同场景比较所需的最小合同。"""

    def run(self, scenario_path: Path, output_root: Path) -> PilotObservation:
        """运行一个受控 Scenario 并返回统一观察。"""
        ...


def run_pilot_pair(
    scenario_path: Path,
    output_root: Path,
    mock: PilotHarnessAdapter,
    openclaw: PilotHarnessAdapter,
) -> PilotScenarioComparison:
    """把完全相同的路径传给两个 Adapter 后机械比较。"""
    mock_observation = mock.run(scenario_path, output_root / "mock")
    openclaw_observation = openclaw.run(scenario_path, output_root / "openclaw")
    return compare_observations(mock_observation, openclaw_observation)
