"""从 T17 Live Raw 哈希索引严格加载 Run、Replay 与观察。"""

from dataclasses import dataclass
from pathlib import Path

from skillflow.experiment.io import sha256_file
from skillflow.experiment.t17.live_attempt_models import (
    T17ArtifactDigest,
    T17LiveTerminalStatus,
    T17LiveUnitKind,
    T17LiveUnitRecord,
)
from skillflow.experiment.t17.live_result_store import load_live_unit_records
from skillflow.experiment.t17.observation_models import ReferenceObservationSnapshot
from skillflow.models.reports import ReplayRiskReport, RunRiskReport


class T17PhaseArtifactError(RuntimeError):
    """Raw 索引中的路径、哈希或报告类型不可信。"""

    __slots__ = ("detail", "identifier")

    def __init__(self, identifier: str, detail: str) -> None:
        """保存相对身份与封闭 reason code。"""
        super().__init__(identifier, detail)
        self.identifier = identifier
        self.detail = detail

    def __str__(self) -> str:
        """返回不含宿主绝对路径的稳定诊断。"""
        return f"{self.identifier}:{self.detail}"


@dataclass(frozen=True, slots=True)
class T17LoadedPhaseArtifacts:
    """已通过 Raw 哈希绑定的阶段成员。"""

    records: tuple[T17LiveUnitRecord, ...]
    runs_by_trial: dict[str, RunRiskReport]
    replays_by_unit: dict[str, ReplayRiskReport]
    observations_by_trial: dict[str, ReferenceObservationSnapshot]

    @property
    def runs(self) -> tuple[RunRiskReport, ...]:
        """按 Raw sequence 返回核心 Run。"""
        return tuple(
            self.runs_by_trial[item.trial_id]
            for item in self.records
            if item.unit_kind is T17LiveUnitKind.CORE
            and item.terminal_status is T17LiveTerminalStatus.COMPLETED
        )

    @property
    def replays(self) -> tuple[ReplayRiskReport, ...]:
        """按 Raw sequence 返回 Replay pair。"""
        return tuple(
            self.replays_by_unit[item.unit_id]
            for item in self.records
            if item.unit_kind is T17LiveUnitKind.REPLAY
            and item.terminal_status is T17LiveTerminalStatus.COMPLETED
        )


def load_phase_artifacts(attempt_root: Path) -> T17LoadedPhaseArtifacts:
    """先复验每个 digest，再解析强类型派生报告。"""
    records = load_live_unit_records(attempt_root / "trial-results.jsonl")
    runs: dict[str, RunRiskReport] = {}
    replays: dict[str, ReplayRiskReport] = {}
    observations: dict[str, ReferenceObservationSnapshot] = {}
    for record in records:
        _verify_record_artifacts(attempt_root, record)
        if record.terminal_status is not T17LiveTerminalStatus.COMPLETED:
            continue
        if record.unit_kind is T17LiveUnitKind.CORE:
            run_path = _artifact_path(
                attempt_root,
                record,
                "/run-report.json",
            )
            observation_path = _artifact_path(
                attempt_root,
                record,
                "/t17-observations.json",
            )
            runs[record.trial_id] = RunRiskReport.model_validate_json(
                run_path.read_text(encoding="utf-8")
            )
            observations[record.trial_id] = ReferenceObservationSnapshot.model_validate_json(
                observation_path.read_text(encoding="utf-8")
            )
        else:
            replay_path = _artifact_path(
                attempt_root,
                record,
                "/replay-report.json",
            )
            replays[record.unit_id] = ReplayRiskReport.model_validate_json(
                replay_path.read_text(encoding="utf-8")
            )
    return T17LoadedPhaseArtifacts(records, runs, replays, observations)


def _verify_record_artifacts(
    attempt_root: Path,
    record: T17LiveUnitRecord,
) -> None:
    for digest in record.artifacts:
        path = _safe_artifact_path(attempt_root, digest)
        if not path.is_file():
            raise T17PhaseArtifactError(record.unit_id, "artifact_missing")
        if sha256_file(path) != digest.sha256:
            raise T17PhaseArtifactError(record.unit_id, "artifact_hash_mismatch")


def _artifact_path(
    attempt_root: Path,
    record: T17LiveUnitRecord,
    suffix: str,
) -> Path:
    digest = next(
        (item for item in record.artifacts if item.relative_path.endswith(suffix)),
        None,
    )
    if digest is None:
        raise T17PhaseArtifactError(record.unit_id, "artifact_index_missing")
    return _safe_artifact_path(attempt_root, digest)


def _safe_artifact_path(
    attempt_root: Path,
    digest: T17ArtifactDigest,
) -> Path:
    root = attempt_root.resolve()
    path = (root / digest.relative_path).resolve()
    if root not in path.parents:
        raise T17PhaseArtifactError(digest.relative_path, "artifact_path_escape")
    return path
