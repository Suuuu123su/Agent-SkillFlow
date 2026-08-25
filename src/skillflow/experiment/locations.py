"""按 Experiment/Run ID 解析 T13 分层目录。"""

from dataclasses import dataclass
from pathlib import Path

from skillflow.experiment.errors import (
    CommandExitCode,
    ExperimentCommandError,
    ExperimentErrorCode,
)


@dataclass(frozen=True, slots=True)
class LocatedRun:
    """一个已存在的 Experiment 与逐 Run 目录。"""

    experiment_root: Path
    run_root: Path


def locate_experiment(runs_root: Path, experiment_id: str) -> Path:
    """兼容总 runs/ 根或直接 Experiment 根。"""
    direct = runs_root if runs_root.name == experiment_id else runs_root / experiment_id
    if (direct / "experiment-manifest.json").is_file():
        return direct
    raise ExperimentCommandError(
        ExperimentErrorCode.RESOURCE_NOT_FOUND,
        f"Experiment 不存在：{experiment_id}",
        CommandExitCode.NOT_FOUND,
    )


def locate_run(runs_root: Path, run_id: str) -> LocatedRun:
    """在一个明确 runs 根的一层 Experiment 中定位唯一 Run。"""
    candidates: list[LocatedRun] = []
    if (runs_root / "runs" / run_id / "run-manifest.json").is_file():
        candidates.append(LocatedRun(runs_root, runs_root / "runs" / run_id))
    if runs_root.is_dir():
        for child in runs_root.iterdir():
            run_root = child / "runs" / run_id
            if child.is_dir() and (run_root / "run-manifest.json").is_file():
                candidates.append(LocatedRun(child, run_root))
    unique = tuple(dict.fromkeys(candidates))
    if len(unique) == 1:
        return unique[0]
    detail = "不存在" if not unique else "在多个 Experiment 中重复"
    raise ExperimentCommandError(
        ExperimentErrorCode.RESOURCE_NOT_FOUND,
        f"Run {detail}：{run_id}",
        CommandExitCode.NOT_FOUND,
    )
