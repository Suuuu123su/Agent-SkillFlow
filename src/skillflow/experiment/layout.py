"""T13 Experiment 目录布局与 Run 资源路径。"""

import hashlib
from dataclasses import dataclass
from pathlib import Path

from skillflow.benchmark.runner import ScenarioRunLayout
from skillflow.experiment.errors import (
    CommandExitCode,
    ExperimentCommandError,
    ExperimentErrorCode,
)


@dataclass(frozen=True, slots=True)
class ExperimentLayout:
    """一个符合 T13 分层合同的 Experiment 根。"""

    root: Path

    @classmethod
    def create(cls, root: Path) -> "ExperimentLayout":
        """原子声明全新根目录，拒绝覆盖已有实验。"""
        try:
            root.mkdir(parents=True, exist_ok=False)
            (root / "runs").mkdir()
            (root / "replays").mkdir()
            (root / "blobs").mkdir()
        except FileExistsError as error:
            raise ExperimentCommandError(
                ExperimentErrorCode.OUTPUT_EXISTS,
                f"Experiment 输出已存在：{root.name}",
                CommandExitCode.OUTPUT_CONFLICT,
            ) from error
        except OSError as error:
            raise ExperimentCommandError(
                ExperimentErrorCode.EXECUTION_FAILED,
                f"无法创建 Experiment：{error.strerror or error.__class__.__name__}",
                CommandExitCode.EXECUTION_FAILED,
            ) from error
        return cls(root)

    def run_layout(self, run_id: str) -> ScenarioRunLayout:
        """返回共享 SQLite、Experiment Blob 与逐 Run 派生产物路径。"""
        namespace = hashlib.sha256(run_id.encode()).hexdigest()[:16]
        run_root = self.root / "runs" / run_id
        return ScenarioRunLayout(
            run_root=run_root,
            experiment_root=self.root,
            database_path=self.root / "state.sqlite",
            workspace_root=self.root / "blobs" / "workspaces" / namespace,
            security_graph_path=run_root / "graph.json",
            risk_report_path=run_root / "run-report.json",
        )
