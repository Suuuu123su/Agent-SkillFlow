"""T13 清单、摘要与报告副本的确定性写入。"""

import csv
import hashlib
import io
from pathlib import Path

from skillflow.experiment.errors import (
    CommandExitCode,
    ExperimentCommandError,
    ExperimentErrorCode,
)
from skillflow.models.base import StrictModel
from skillflow.models.reports import ExperimentRiskReport, RunRiskReport


def write_json_model(path: Path, model: StrictModel) -> None:
    """以不可覆盖方式写入一个 Pydantic JSON 文档。"""
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(model.model_dump_json(indent=2, by_alias=True))
            stream.write("\n")
    except FileExistsError as error:
        raise ExperimentCommandError(
            ExperimentErrorCode.OUTPUT_EXISTS,
            f"目标文件已存在：{path.name}",
            CommandExitCode.OUTPUT_CONFLICT,
        ) from error
    except OSError as error:
        raise ExperimentCommandError(
            ExperimentErrorCode.EXECUTION_FAILED,
            f"无法写入 {path.name}：{error.strerror or error.__class__.__name__}",
            CommandExitCode.EXECUTION_FAILED,
        ) from error


def replace_json_model(path: Path, model: StrictModel) -> None:
    """以同目录临时文件原子更新一个已存在的派生 JSON。"""
    temporary = path.with_name(f".{path.name}.next")
    write_json_model(temporary, model)
    try:
        temporary.replace(path)
    except OSError as error:
        raise ExperimentCommandError(
            ExperimentErrorCode.EXECUTION_FAILED,
            f"无法更新 {path.name}：{error.strerror or error.__class__.__name__}",
            CommandExitCode.EXECUTION_FAILED,
        ) from error


def sha256_file(path: Path) -> str:
    """返回一个派生产物的字节级 SHA-256。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_summary_csv(
    path: Path,
    runs: tuple[RunRiskReport, ...],
    experiment: ExperimentRiskReport,
) -> None:
    """逐 Run 写出基础指标，并保留所有比例的原始分子分母。"""
    content = summary_csv_content(runs, experiment)
    try:
        with path.open("x", encoding="utf-8", newline="") as stream:
            stream.write(content)
    except FileExistsError as error:
        raise ExperimentCommandError(
            ExperimentErrorCode.OUTPUT_EXISTS,
            f"目标文件已存在：{path.name}",
            CommandExitCode.OUTPUT_CONFLICT,
        ) from error
    except OSError as error:
        raise ExperimentCommandError(
            ExperimentErrorCode.EXECUTION_FAILED,
            f"无法写入 {path.name}：{error.strerror or error.__class__.__name__}",
            CommandExitCode.EXECUTION_FAILED,
        ) from error


def replace_summary_csv(
    path: Path,
    runs: tuple[RunRiskReport, ...],
    experiment: ExperimentRiskReport,
) -> None:
    """原子更新由标准报告机械生成的 CSV。"""
    temporary = path.with_name(f".{path.name}.next")
    try:
        with temporary.open("x", encoding="utf-8", newline="") as stream:
            stream.write(summary_csv_content(runs, experiment))
        temporary.replace(path)
    except OSError as error:
        raise ExperimentCommandError(
            ExperimentErrorCode.EXECUTION_FAILED,
            f"无法更新 {path.name}：{error.strerror or error.__class__.__name__}",
            CommandExitCode.EXECUTION_FAILED,
        ) from error


def summary_csv_content(
    runs: tuple[RunRiskReport, ...],
    experiment: ExperimentRiskReport,
) -> str:
    """返回保留全部原始分子分母的确定性 CSV。"""
    header = (
        "experiment_id",
        "run_id",
        "scenario",
        "variant",
        "seed",
        "backend",
        "run_role",
        "task_success",
        "harm",
        "UEA_count",
        "UEA_type_count",
        "UEA_weight",
        "ProvPrecision_numerator",
        "ProvPrecision_denominator",
        "ProvPrecision",
        "ProvRecall_numerator",
        "ProvRecall_denominator",
        "ProvRecall",
        "ProvF1_numerator",
        "ProvF1_denominator",
        "ProvF1",
        "ALR_numerator",
        "ALR_denominator",
        "RIR_1_numerator",
        "RIR_1_denominator",
        "RIR_3_numerator",
        "RIR_3_denominator",
    )
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(header)
    for report in runs:
        overall = report.provenance.overall
        writer.writerow(
            (
                report.experiment_id or "",
                report.run_id,
                report.scenario.root if report.scenario is not None else "",
                report.variant or "",
                "" if report.seed is None else report.seed,
                report.backend or "",
                report.run_role.value,
                report.task_success,
                report.harm,
                report.uea.uea_count,
                report.uea.uea_type_count,
                report.uea.uea_weight,
                overall.precision.numerator,
                overall.precision.denominator,
                overall.precision.value,
                overall.recall.numerator,
                overall.recall.denominator,
                overall.recall.value,
                overall.f1.numerator,
                overall.f1.denominator,
                overall.f1.value,
                experiment.alr.numerator,
                experiment.alr.denominator,
                experiment.rir_1.numerator,
                experiment.rir_1.denominator,
                experiment.rir_3.numerator,
                experiment.rir_3.denominator,
            )
        )
    return stream.getvalue()
