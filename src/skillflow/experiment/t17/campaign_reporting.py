"""T17 Supervisor 的跨模型、Defense 与最终派生报告编排。"""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from skillflow.experiment.t17.cross_model_report import (
    write_cross_model_report,
)
from skillflow.experiment.t17.defense_report import (
    T17DefenseReportRequest,
    write_defense_report,
)
from skillflow.experiment.t17.final_models import T17FinalMetricsReport
from skillflow.experiment.t17.final_report import write_final_metrics_report
from skillflow.experiment.t17.live_matrix import T17LiveStage


class T17SupervisorSequenceError(RuntimeError):
    """Campaign 缺少生成派生报告所需的前置阶段。"""

    __slots__ = ("stage",)

    def __init__(self, stage: T17LiveStage) -> None:
        """保存缺失阶段。"""
        super().__init__(stage.value)
        self.stage = stage

    def __str__(self) -> str:
        """返回稳定诊断。"""
        return f"t17_stage_missing:{self.stage.value}"


class T17PreparedStageView(Protocol):
    """派生报告只需阶段和 Attempt 根。"""

    @property
    def stage(self) -> T17LiveStage:
        """返回阶段。"""
        ...

    @property
    def attempt_root(self) -> Path:
        """返回 Attempt 根。"""
        ...


class T17StageResultView(Protocol):
    """避免 Campaign reporter 反向导入 Supervisor 具体类型。"""

    @property
    def prepared(self) -> T17PreparedStageView:
        """返回只读阶段视图。"""
        ...


@dataclass(frozen=True, slots=True)
class T17CampaignReportingContext:
    """派生报告所需的项目、Campaign 与已完成阶段。"""

    project_root: Path
    campaign_root: Path
    results: tuple[T17StageResultView, ...]


def update_campaign_reports(
    context: T17CampaignReportingContext,
    stage_result: T17StageResultView,
) -> T17FinalMetricsReport | None:
    """Model2 写 cross-model；Defense 写 defense/final。"""
    stage = stage_result.prepared.stage
    if stage is T17LiveStage.MODEL2:
        model1 = _require_stage(context.results, T17LiveStage.MODEL1)
        write_cross_model_report(
            model1.prepared.attempt_root / "phase-metrics.json",
            stage_result.prepared.attempt_root / "phase-metrics.json",
            context.campaign_root / "cross-model.json",
        )
    if stage is not T17LiveStage.DEFENSE:
        return None
    model1 = _require_stage(context.results, T17LiveStage.MODEL1)
    cross_path = context.campaign_root / "cross-model.json"
    defense_path = context.campaign_root / "defense-report.json"
    t17_root = context.project_root / "experiments" / "t17"
    write_defense_report(
        T17DefenseReportRequest(
            model1_attempt=model1.prepared.attempt_root,
            defense_attempt=stage_result.prepared.attempt_root,
            model1_matrix_path=t17_root / "matrix_model1.yaml",
            defense_matrix_path=t17_root / "matrix_defense.yaml",
            registry_path=t17_root / "scenario_measurements.yaml",
            base_matrix_path=(context.project_root / "scenarios" / "matrix" / "mvp.yaml"),
            output_path=defense_path,
        )
    )
    phase_paths = tuple(
        _require_stage(context.results, item).prepared.attempt_root / "phase-metrics.json"
        for item in (
            T17LiveStage.CANARY,
            T17LiveStage.MODEL1,
            T17LiveStage.MODEL2_CANARY,
            T17LiveStage.MODEL2,
            T17LiveStage.DEFENSE,
        )
    )
    return write_final_metrics_report(
        phase_paths,
        cross_path,
        defense_path,
        context.campaign_root / "final-metrics.json",
        context.campaign_root / "final-summary.csv",
    )


def _require_stage(
    results: tuple[T17StageResultView, ...],
    stage: T17LiveStage,
) -> T17StageResultView:
    result = next(
        (item for item in results if item.prepared.stage is stage),
        None,
    )
    if result is None:
        raise T17SupervisorSequenceError(stage)
    return result
