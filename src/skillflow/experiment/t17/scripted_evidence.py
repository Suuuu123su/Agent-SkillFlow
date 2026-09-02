"""从每 Run Observation 与 Replay 报告计算独立覆盖率。"""

from dataclasses import dataclass
from pathlib import Path

from skillflow.experiment.t17.contracts import MeasurementStatus, RatioMeasurement
from skillflow.experiment.t17.observations import (
    ReferenceObservationSnapshot,
    build_influence_observations,
)
from skillflow.models.replay_reports import ReplayRiskReport

EXPECTED_CORE_OBSERVATIONS = 24


@dataclass(frozen=True, slots=True)
class ScriptedEvidenceCoverage:
    """Task、Receipt、Hook 的独立分子分母。"""

    task_success: RatioMeasurement
    receipts: RatioMeasurement
    hooks: RatioMeasurement
    snapshots: tuple[ReferenceObservationSnapshot, ...]


@dataclass(frozen=True, slots=True)
class ScriptedEvidenceError(ValueError):
    """Run Observation 缺失或 required Hook 未测得。"""

    identifier: str
    detail: str

    def __str__(self) -> str:
        """返回稳定证据门诊断。"""
        return f"{self.identifier}:{self.detail}"


def load_scripted_evidence(
    experiment_root: Path,
    replays: tuple[ReplayRiskReport, ...],
) -> ScriptedEvidenceCoverage:
    """从 24 个独立 Observation 和 18 个 Replay 计算覆盖率。"""
    snapshots = tuple(
        ReferenceObservationSnapshot.model_validate_json(
            (directory / "t17-observations.json").read_text(encoding="utf-8")
        )
        for directory in sorted(
            (experiment_root / "runs").iterdir(),
            key=lambda item: item.name,
        )
    )
    if len(snapshots) != EXPECTED_CORE_OBSERVATIONS:
        raise ScriptedEvidenceError(experiment_root.name, "expected_24_observations")
    task_measured = sum(item.task_success is not None for item in snapshots)
    executed = tuple(
        effect for snapshot in snapshots for effect in snapshot.effects if effect.executed
    )
    receipted = sum(effect.receipt_id is not None for effect in executed)
    required_hooks = tuple(
        hook
        for snapshot in snapshots
        for hook in snapshot.hooks
        if hook.status is not MeasurementStatus.NOT_APPLICABLE
    )
    unavailable = tuple(
        hook for hook in required_hooks if hook.status is not MeasurementStatus.MEASURED
    )
    if unavailable:
        raise ScriptedEvidenceError(
            unavailable[0].hook.value,
            unavailable[0].status.value,
        )
    influences = build_influence_observations(replays)
    hook_denominator = len(required_hooks) + len(replays)
    hook_numerator = len(required_hooks) + len(influences)
    evidence_ids = tuple(item.run_id for item in snapshots)
    return ScriptedEvidenceCoverage(
        task_success=_ratio(task_measured, len(snapshots), evidence_ids),
        receipts=_ratio(receipted, len(executed), evidence_ids),
        hooks=_ratio(hook_numerator, hook_denominator, evidence_ids),
        snapshots=snapshots,
    )


def _ratio(
    numerator: int,
    denominator: int,
    evidence_ids: tuple[str, ...],
) -> RatioMeasurement:
    if denominator == 0:
        raise ScriptedEvidenceError("ratio", "zero_denominator")
    return RatioMeasurement(
        status=MeasurementStatus.MEASURED,
        numerator=numerator,
        denominator=denominator,
        scheduled_denominator=denominator,
        value=numerator / denominator,
        evidence_ids=evidence_ids,
    )
