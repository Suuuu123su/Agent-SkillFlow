"""T13 研究工作流的根级 CLI 命令。"""

from enum import StrEnum, unique
from pathlib import Path
from typing import Annotated, Never

import typer

from skillflow.experiment.aggregate import aggregate_experiment
from skillflow.experiment.analyze import analyze_persisted_run
from skillflow.experiment.errors import (
    CommandExitCode,
    ExperimentCommandError,
    ExperimentErrorCode,
)
from skillflow.experiment.exporting import ExportScope, export_report
from skillflow.experiment.factorial import execute_factorial
from skillflow.experiment.graphing import graph_json
from skillflow.experiment.matrix import MatrixExecutionRequest, execute_matrix
from skillflow.experiment.replay import replay_persisted_run
from skillflow.experiment.single import execute_single_run
from skillflow.models.enums import EnforcementMode
from skillflow.models.execution import ExecutionBackend
from skillflow.models.matrix import ExperimentMatrix
from skillflow.models.matrix_design import HarnessFeature
from skillflow.validation import DocumentValidationError, validate_yaml_document


@unique
class GraphFormat(StrEnum):
    """T13 MVP 支持的图导出格式。"""

    JSON = "json"


def register_research_commands(root: typer.Typer) -> None:
    """把 T13 命令注册到既有根应用。"""
    root.command("run")(run_command)
    root.command("analyze")(analyze_command)
    root.command("graph")(graph_command)
    root.command("factorial")(factorial_command)
    root.command("matrix")(matrix_command)
    root.command("replay")(replay_command)
    root.command("aggregate")(aggregate_command)
    root.command("export")(export_command)


def run_command(
    scenario: Annotated[Path, typer.Argument(help="待运行的 Scenario YAML。")],
    mode: Annotated[EnforcementMode, typer.Option(help="monitor 或 enforce。")] = (
        EnforcementMode.MONITOR
    ),
    output: Annotated[Path | None, typer.Option(help="Experiment 输出目录。")] = None,
    redact: Annotated[
        bool,
        typer.Option("--redact/--no-redact", help="默认脱敏报告与导出。"),
    ] = True,
) -> None:
    """运行一个 Scenario，并建立 single-run Experiment。"""
    try:
        result = execute_single_run(scenario, mode, output, redact)
    except DocumentValidationError as error:
        _document_failure(error)
    except ExperimentCommandError as error:
        _experiment_failure(error)
    typer.echo(
        f"[通过] Experiment={result.experiment_id} Run={result.run_id} 输出={result.output_root}"
    )


def analyze_command(
    run_id: Annotated[str, typer.Argument(help="待分析的 Run ID。")],
    runs_root: Annotated[Path, typer.Option(help="Experiment 根目录。")] = Path("runs"),
) -> None:
    """从持久化事实重新计算一个 Run 报告。"""
    try:
        result = analyze_persisted_run(run_id, runs_root)
    except (DocumentValidationError, ExperimentCommandError) as error:
        _known_failure(error)
    typer.echo(f"[通过] Run={result.run_id} 报告={result.report_path}")


def graph_command(
    run_id: Annotated[str, typer.Argument(help="待重建图的 Run ID。")],
    output_format: Annotated[
        GraphFormat,
        typer.Option("--format", help="图输出格式。"),
    ] = GraphFormat.JSON,
    runs_root: Annotated[Path, typer.Option(help="Experiment 根目录。")] = Path("runs"),
) -> None:
    """从 Experiment SQLite 重建脱敏安全图。"""
    try:
        content = graph_json(run_id, runs_root)
    except ExperimentCommandError as error:
        _experiment_failure(error)
    if output_format is GraphFormat.JSON:
        typer.echo(content)


def factorial_command(
    scenario: Annotated[Path, typer.Argument(help="基础 Scenario YAML。")],
    feature: Annotated[str, typer.Option(help="待切换的 Harness feature。")],
    seeds: Annotated[list[int] | None, typer.Option(help="可重复提供的整数 seed。")] = None,
    output: Annotated[Path | None, typer.Option(help="Experiment 输出目录。")] = None,
) -> None:
    """执行一个受控 Harness feature 的二水平因子实验。"""
    try:
        selected = _harness_feature(feature)
        result = execute_factorial(scenario, selected, tuple(seeds or (0,)), output)
    except (DocumentValidationError, ExperimentCommandError) as error:
        _known_failure(error)
    typer.echo(
        f"[通过] Experiment={result.experiment_id} Runs={result.run_count} "
        f"输出={result.output_root}"
    )


def matrix_command(
    matrix: Annotated[Path, typer.Argument(help="Experiment Matrix YAML。")],
    backend: Annotated[str, typer.Option(help="MVP 固定为 scripted。")] = "scripted",
    output: Annotated[Path | None, typer.Option(help="Experiment 输出目录。")] = None,
    determinism_repeats: Annotated[
        int | None,
        typer.Option(help="覆盖 Matrix 中的确定性重复次数。"),
    ] = None,
    redact: Annotated[
        bool,
        typer.Option("--redact/--no-redact", help="默认脱敏报告与导出。"),
    ] = True,
) -> None:
    """执行已校验 Matrix 并生成分层报告。"""
    try:
        document = validate_yaml_document(matrix, ExperimentMatrix)
        _scripted_backend(backend)
        result = execute_matrix(
            MatrixExecutionRequest(matrix, document, output, determinism_repeats, redact)
        )
    except DocumentValidationError as error:
        _document_failure(error)
    except ExperimentCommandError as error:
        _experiment_failure(error)
    typer.echo(
        f"[通过] Experiment={result.experiment_id} Runs={result.run_count} "
        f"Replays={result.replay_count} 输出={result.output_root}"
    )


def replay_command(
    run_id: Annotated[str, typer.Argument(help="原始 Run ID。")],
    neutralize_artifact: Annotated[
        str,
        typer.Option(help="要中和的原始 Run Artifact ID。"),
    ],
    runs_root: Annotated[Path, typer.Option(help="Experiment 根目录。")] = Path("runs"),
) -> None:
    """按已注册 alias 对一个 Run 执行成对反事实重放。"""
    try:
        result = replay_persisted_run(run_id, neutralize_artifact, runs_root)
    except (DocumentValidationError, ExperimentCommandError) as error:
        _known_failure(error)
    typer.echo(f"[通过] Replay={result.replay_id} 输出={result.output_root}")


def aggregate_command(
    experiment_id: Annotated[str, typer.Argument(help="待聚合的 Experiment ID。")],
    runs_root: Annotated[Path, typer.Option(help="Experiment 根目录。")] = Path("runs"),
) -> None:
    """只读取标准 Run/Replay 结果重算 Experiment 报告。"""
    try:
        result = aggregate_experiment(experiment_id, runs_root)
    except (DocumentValidationError, ExperimentCommandError) as error:
        _known_failure(error)
    typer.echo(
        f"[通过] Experiment={result.experiment_id} Runs={result.run_count} "
        f"Replays={result.replay_count}"
    )


def export_command(
    scope: Annotated[ExportScope, typer.Option(help="run 或 experiment。")],
    identifier: Annotated[str, typer.Argument(help="Run 或 Experiment ID。")],
    output: Annotated[Path, typer.Option(help="不可覆盖的目标 JSON 文件。")],
    runs_root: Annotated[Path, typer.Option(help="Experiment 根目录。")] = Path("runs"),
    redact: Annotated[
        bool,
        typer.Option("--redact/--no-redact", help="默认脱敏导出。"),
    ] = True,
) -> None:
    """导出一个经过 Schema 校验的标准报告。"""
    try:
        result = export_report(scope, identifier, output, runs_root, redact)
    except ExperimentCommandError as error:
        _experiment_failure(error)
    typer.echo(f"[通过] Scope={result.scope.value} ID={result.identifier} 输出={result.output}")


def _pending(command: str) -> Never:
    error = ExperimentCommandError(
        ExperimentErrorCode.NOT_IMPLEMENTED,
        f"{command} 正在由 T13 实现",
        CommandExitCode.EXECUTION_FAILED,
    )
    typer.echo(f"[失败] {error}", err=True)
    raise typer.Exit(code=int(error.exit_code)) from error


def _document_failure(error: DocumentValidationError) -> Never:
    for issue in error.issues:
        typer.echo(issue.render(), err=True)
    raise typer.Exit(code=int(CommandExitCode.INPUT_INVALID)) from error


def _experiment_failure(error: ExperimentCommandError) -> Never:
    typer.echo(f"[失败] {error}", err=True)
    raise typer.Exit(code=int(error.exit_code)) from error


def _known_failure(error: DocumentValidationError | ExperimentCommandError) -> Never:
    if isinstance(error, DocumentValidationError):
        _document_failure(error)
    _experiment_failure(error)


def _scripted_backend(value: str) -> ExecutionBackend:
    try:
        backend = ExecutionBackend(value)
    except ValueError as error:
        raise ExperimentCommandError(
            ExperimentErrorCode.INPUT_VALUE_INVALID,
            "backend 仅支持 scripted",
            CommandExitCode.INPUT_INVALID,
        ) from error
    return backend


def _harness_feature(value: str) -> HarnessFeature:
    try:
        return HarnessFeature(value)
    except ValueError as error:
        raise ExperimentCommandError(
            ExperimentErrorCode.INPUT_VALUE_INVALID,
            "feature 不是受支持的 Harness 布尔轴",
            CommandExitCode.INPUT_INVALID,
        ) from error
