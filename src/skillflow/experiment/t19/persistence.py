"""T19 独占落盘与可恢复的私有检查点；不保存任何密钥。"""

import os
from pathlib import Path

from pydantic import BaseModel

from skillflow.adapters.checkpoint import verify_harness_checkpoint
from skillflow.benchmark.replay_models import ReplayBranchResult, ReplaySourceState
from skillflow.benchmark.scenario_execution import ScenarioExecutionSnapshot
from skillflow.defense.rx_provider import RxTrace
from skillflow.experiment.t17.v2.run_models import UnitUsage
from skillflow.experiment.t17.v2.runtime_models import DecisionFact, ExecutionIssue
from skillflow.experiment.t17.v2.unit_execution import PrivateCheckpoint
from skillflow.experiment.t19.boundaries import BoundaryIssue
from skillflow.experiment.t19.recovery import LimitFact, RecoveryFact
from skillflow.models.base import StrictModel
from skillflow.models.references import FixtureImplementationRef


class PrivateReplaySource(PrivateCheckpoint):
    """复用完整检查点合同，补齐恢复编排游标与目标 ID。"""

    execution: ScenarioExecutionSnapshot
    source_artifact_id: str
    prefix_steps: int = 0

    def source(self) -> ReplaySourceState:
        """恢复前重新核验内容与前缀哈希。"""
        verify_harness_checkpoint(self.checkpoint)
        return ReplaySourceState(self.checkpoint, self.execution, self.source_artifact_id)


PrivateReplaySource.model_rebuild(
    _types_namespace={"FixtureImplementationRef": FixtureImplementationRef}
)


class SavedBranch(StrictModel):
    """完成分支的受信结果与费用，支持配对收尾阶段的无调用恢复。"""

    result: ReplayBranchResult
    usage: UnitUsage
    decisions: tuple[DecisionFact, ...] = ()
    issues: tuple[ExecutionIssue, ...] = ()
    recoveries: tuple[RecoveryFact, ...] = ()
    limits: tuple[LimitFact, ...] = ()
    traces: tuple[RxTrace, ...] = ()
    boundary_issues: tuple[BoundaryIssue, ...] = ()


SavedBranch.model_rebuild(_types_namespace={"FixtureImplementationRef": FixtureImplementationRef})


def write_record(path: Path, record: BaseModel) -> None:
    """独占创建并同步磁盘，已有结果不覆盖。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(record.model_dump_json() + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def save_source(path: Path, source: ReplaySourceState, *, prefix_steps: int = 0) -> None:
    """只用数据合同序列化，无可执行对象反序列化。"""
    record = PrivateReplaySource(
        checkpoint=source.checkpoint,
        execution=source.execution,
        source_artifact_id=source.source_artifact_id,
        prefix_steps=prefix_steps,
    )
    write_record(path, record)
    restored = PrivateReplaySource.model_validate_json(path.read_text(encoding="utf-8")).source()
    if restored != source:
        raise ValueError("t19_checkpoint_roundtrip_mismatch")
