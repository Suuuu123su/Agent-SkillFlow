"""完整第二版的中文入口；离线命令不访问网络。"""

from pathlib import Path
from typing import Annotated, Never

import typer
from jsonschema.exceptions import ValidationError as JsonSchemaError

from skillflow.experiment.t17.live_matrix import T17LiveStage
from skillflow.experiment.t17.reference_backend import ReferenceModelClient
from skillflow.experiment.t17.v2.campaign_cli import cost_plan_command, live_command
from skillflow.experiment.t17.v2.config_models import V2Configuration
from skillflow.experiment.t17.v2.csv_export import comparison_rows, metric_rows
from skillflow.experiment.t17.v2.csv_models import ComparisonCsvRow, MetricCsvRow
from skillflow.experiment.t17.v2.dataset_analysis import dataset_reports
from skillflow.experiment.t17.v2.dataset_io import export_dataset, load_dataset
from skillflow.experiment.t17.v2.dataset_models import DatasetReports
from skillflow.experiment.t17.v2.dataset_reports_io import write_reports
from skillflow.experiment.t17.v2.dataset_rows import HashManifest
from skillflow.experiment.t17.v2.dataset_writing import DatasetWriter
from skillflow.experiment.t17.v2.fake_client import V2FakeClient
from skillflow.experiment.t17.v2.golden import run_golden
from skillflow.experiment.t17.v2.loading import load_stage, read_model
from skillflow.experiment.t17.v2.matrix import build_matrix
from skillflow.experiment.t17.v2.schema_models import write_v2_schemas
from skillflow.experiment.t17.v2.stage import StageSetup, run_stage
from skillflow.experiment.t17.v2.static_protocol import freeze_protocol
from skillflow.validation import DocumentValidationError

v2_app = typer.Typer(
    help="完整 T17 第二版：冻结、离线验证、真实实验和可复算报告。", no_args_is_help=True
)
_FAILURES = (ValueError, OSError, JsonSchemaError, DocumentValidationError)
v2_app.command("cost-plan")(cost_plan_command)
v2_app.command("run-live")(live_command)


@v2_app.command("freeze")
def freeze_command(
    output: Annotated[Path, typer.Option(help="尚不存在的项目内冻结目录。")],
    configuration: Annotated[Path | None, typer.Option(help="可选的已登记技能配置。")] = None,
) -> None:
    """机械冻结五个阶段；不申请密钥或发送请求。"""
    try:
        manifest = freeze_protocol(Path.cwd(), output, configuration)
    except _FAILURES as error:
        fail(error)
    typer.echo(f"[通过] 第二版配置已冻结 文件={len(manifest.files)} API=0")


@v2_app.command("schemas")
def schemas_command(
    output: Annotated[Path, typer.Option(help="只创建新的第二版格式文件。")],
) -> None:
    """由类型模型生成格式，不覆盖现有文件。"""
    try:
        _inside(output)
        write_v2_schemas(output)
    except _FAILURES as error:
        fail(error)
    typer.echo("[通过] 第二版格式已生成 API=0")


@v2_app.command("run-scripted")
def scripted_command(
    configuration: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    output: Annotated[Path, typer.Option(help="全新执行目录。")],
    stage: T17LiveStage = T17LiveStage.CANARY,
) -> None:
    """以预设脚本验证实际执行链；不产生模型实测结果。"""
    _offline(configuration, output, stage, None)


@v2_app.command("run-fake")
def fake_command(
    configuration: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    output: Annotated[Path, typer.Option(help="全新执行目录。")],
    request_all: Annotated[bool, typer.Option(help="固定选择全部或不选择工具动作。")] = True,
    stage: T17LiveStage = T17LiveStage.CANARY,
) -> None:
    """以纯本地选择器验证模型接口及无调用路径。"""
    _offline(configuration, output, stage, V2FakeClient(request_all))


def _offline(
    configuration: Path, output: Path, stage: T17LiveStage, client: ReferenceModelClient | None
) -> None:
    try:
        config = read_model(configuration, V2Configuration)
        matrix = build_matrix(Path.cwd(), config, stage)
        result = run_stage(
            StageSetup(
                Path.cwd(),
                output,
                config,
                matrix,
                "scripted" if client is None else "fake_reference",
                client,
            )
        )
    except _FAILURES as error:
        fail(error)
    typer.echo(
        f"第二版离线：任务={len(result.cores)} 重放={len(result.replays)} "
        f"完整验收={result.gate.passed} API=0"
    )
    if not result.gate.passed:
        raise typer.Exit(code=2)


@v2_app.command("report")
def report_command(
    output: Annotated[Path, typer.Option(help="全新标准数据集目录。")],
    dataset: Annotated[Path | None, typer.Option(help="仅使用已有标准数据集重算。")] = None,
    attempt: Annotated[
        list[Path] | None, typer.Option(help="可重复指定不同阶段的独立原始目录。")
    ] = None,
) -> None:
    """逐条复核事实与全部表格，禁止同阶段不同尝试拼接。"""
    try:
        if (dataset is None) == (not attempt):
            raise ValueError("v2_exactly_one_input_kind")
        stages = (
            load_dataset(dataset)
            if dataset is not None
            else tuple(load_stage(Path.cwd(), p) for p in (attempt or []))
        )
        manifest = export_dataset(Path.cwd(), output, stages)
    except _FAILURES as error:
        fail(error)
    typer.echo(
        f"[通过] 已重算标准数据 任务={manifest.scheduled_core} 重放={manifest.scheduled_replay}"
    )
    if not manifest.all_provided_stages_passed:
        raise typer.Exit(code=2)


def compare_skills_command(
    dataset: Annotated[Path, typer.Option(exists=True, file_okay=False)],
    output: Annotated[Path, typer.Option(help="全新技能分层报告目录。")],
) -> None:
    """按实际技能内容版本和相同条件输出完整向量与配对差。"""
    try:
        stages = load_dataset(dataset)
        all_reports = dataset_reports(stages)
        reports = DatasetReports(
            vectors=tuple(v for v in all_reports.vectors if v.kind == "skill"),
            comparisons=tuple(c for c in all_reports.comparisons if c.kind == "skill"),
        )
        writer = DatasetWriter(Path.cwd(), output)
        write_reports(writer, "skill-comparison.json", reports)
        writer.csv("skill-metrics.csv", metric_rows(reports), MetricCsvRow)
        writer.csv("skill-pairs.csv", comparison_rows(reports, "skill"), ComparisonCsvRow)
        writer.model(
            "sha256-manifest.json",
            HashManifest(files={n: f.content for n, f in writer.files.items()}),
        )
    except _FAILURES as error:
        fail(error)
    typer.echo(
        f"[通过] 技能分层={len(reports.vectors)} 配对={len(reports.comparisons)}；未追加实验"
    )


def _inside(output: Path) -> None:
    if not output.resolve().is_relative_to(Path.cwd()) or output.resolve() == Path.cwd():
        raise ValueError("v2_output_outside_project")


@v2_app.command("golden")
def golden_command(
    protocol: Annotated[Path, typer.Option(exists=True, file_okay=False)],
    output: Annotated[Path, typer.Option(help="全新固定脚本验收目录。")],
) -> None:
    """24/18 主执行及五次核心确定性，不调用 API。"""
    try:
        report = run_golden(Path.cwd(), protocol, output)
    except _FAILURES as error:
        fail(error)
    typer.echo(
        f"固定脚本：任务={report.core} 重放={report.replay} "
        f"确定性复跑={report.replicas} 验收={report.passed} API=0"
    )
    if not report.passed:
        raise typer.Exit(code=2)


def fail(error: BaseException) -> Never:
    """只显示错误类型，不回显可能含正文或凭据的异常消息。"""
    typer.echo("[失败] 第二版 " + type(error).__name__ + "；已有证据保留", err=True)
    raise typer.Exit(code=2) from error
