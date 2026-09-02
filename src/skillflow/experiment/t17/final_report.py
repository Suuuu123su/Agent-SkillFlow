"""T17 Phase/CrossModel/Defense 最终 JSON 与长表 CSV。"""

import csv
from pathlib import Path

from skillflow.experiment.io import sha256_file, write_json_model
from skillflow.experiment.t17.comparison_models import T17CrossModelReport
from skillflow.experiment.t17.contracts import RatioMeasurement
from skillflow.experiment.t17.defense_models import T17DefenseReport
from skillflow.experiment.t17.final_models import T17FinalMetricsReport
from skillflow.experiment.t17.metric_models import T17PhaseMetricsReport

EXPECTED_PHASE_COUNT = 5


def build_final_metrics_report(
    phase_paths: tuple[Path, ...],
    cross_model_path: Path,
    defense_path: Path,
) -> T17FinalMetricsReport:
    """加载五个 Phase 并保留所有模型独立分母。"""
    phases = tuple(
        T17PhaseMetricsReport.model_validate_json(path.read_text(encoding="utf-8"))
        for path in phase_paths
    )
    cross = T17CrossModelReport.model_validate_json(cross_model_path.read_text(encoding="utf-8"))
    defense = T17DefenseReport.model_validate_json(defense_path.read_text(encoding="utf-8"))
    return T17FinalMetricsReport(
        phases=phases,
        cross_model=cross,
        defense=defense,
        source_sha256={
            **{
                f"phase:{index}": sha256_file(path)
                for index, path in enumerate(phase_paths, start=1)
            },
            "cross_model": sha256_file(cross_model_path),
            "defense": sha256_file(defense_path),
        },
        complete=(
            len(phases) == EXPECTED_PHASE_COUNT
            and all(item.required_metrics_complete for item in phases)
            and cross.complete
            and defense.complete
        ),
    )


def write_final_metrics_report(
    phase_paths: tuple[Path, ...],
    cross_model_path: Path,
    defense_path: Path,
    json_output: Path,
    csv_output: Path,
) -> T17FinalMetricsReport:
    """不可覆盖写出最终 JSON 与保存状态/分子的长表 CSV。"""
    report = build_final_metrics_report(
        phase_paths,
        cross_model_path,
        defense_path,
    )
    write_json_model(json_output, report)
    _write_summary_csv(csv_output, report)
    return report


def _write_summary_csv(
    path: Path,
    report: T17FinalMetricsReport,
) -> None:
    rows = []
    for phase in report.phases:
        for name, measurement in _phase_ratios(phase):
            rows.append(
                (
                    phase.stage_summary.stage.value,
                    phase.evidence_domain.model_revision or "",
                    name,
                    measurement.status.value,
                    measurement.numerator,
                    measurement.denominator,
                    measurement.scheduled_denominator,
                    measurement.value,
                )
            )
    try:
        with path.open("x", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(
                (
                    "stage",
                    "model_revision",
                    "metric",
                    "status",
                    "numerator",
                    "denominator",
                    "scheduled_denominator",
                    "value",
                )
            )
            writer.writerows(rows)
    except OSError as error:
        raise T17FinalReportWriteError(path.name) from error


def _phase_ratios(
    phase: T17PhaseMetricsReport,
) -> tuple[tuple[str, RatioMeasurement], ...]:
    return (
        ("completion", phase.stage_summary.completion),
        ("task_success", phase.task_success_rate),
        ("safe_task_success", phase.safe_task_success_rate),
        ("benign_refusal", phase.benign_refusal_rate),
        ("verified_target_effect", phase.verified_target_effect_rate),
        ("uea_affected_trial", phase.uea.affected_trial_rate),
        ("replay_nonzero_ci", phase.causal_impact.nonzero_rate),
        ("cluster_consistency", phase.cluster_consistency),
    )


class T17FinalReportWriteError(RuntimeError):
    """最终 CSV 无法不可覆盖写出。"""

    __slots__ = ("filename",)

    def __init__(self, filename: str) -> None:
        """保存项目内文件名。"""
        super().__init__(filename)
        self.filename = filename

    def __str__(self) -> str:
        """返回稳定诊断。"""
        return f"final_report_write_failed:{self.filename}"
