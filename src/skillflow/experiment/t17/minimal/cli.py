"""最小离线链路的 freeze/run/report CLI；没有付费入口。"""

from pathlib import Path
from typing import Annotated, Never

import typer
from jsonschema.exceptions import ValidationError as JsonSchemaError

from skillflow.experiment.t17.minimal.artifacts import freeze_minimal_configuration
from skillflow.experiment.t17.minimal.reporting import write_minimal_report
from skillflow.experiment.t17.minimal.run_models import MinimalDomain
from skillflow.experiment.t17.minimal.runner import run_minimal_domain
from skillflow.validation import DocumentValidationError

minimal_app = typer.Typer(help="T17 单实例、单重复、零 API 的最小技术验证。", no_args_is_help=True)


@minimal_app.command("freeze")
def freeze_command(output: Annotated[Path, typer.Option(help="全新冻结配置目录。")]) -> None:
    """机械生成获准的 23 core/12 Replay 配置，拒绝覆盖。"""
    try:
        _inside_project(output)
        freeze_minimal_configuration(Path(), output)
    except (ValueError, OSError, JsonSchemaError, DocumentValidationError) as error:
        _failure(error)
    typer.echo("[通过] minimal freeze core=23 replay=12 API=0")


@minimal_app.command("run")
def run_command(
    configuration: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    output: Annotated[Path, typer.Option(help="全新执行目录；绝不恢复已有 Attempt。")],
    domain: Annotated[str, typer.Option(help="scripted 或 fake_reference。")],
) -> None:
    """沿 YAML/Runtime/Trace/Replay 执行一个独立域。"""
    try:
        _inside_project(output)
        selected = _domain(domain)
        result = run_minimal_domain(configuration, output, domain=selected)
    except (ValueError, OSError, JsonSchemaError, DocumentValidationError) as error:
        _failure(error)
    typer.echo(
        f"[通过] minimal {domain} core={result.run_count} replay={result.replay_count} API=0"
    )


@minimal_app.command("report")
def report_command(
    raw: Annotated[Path, typer.Option(exists=True, file_okay=False)],
    output: Annotated[Path, typer.Option(help="Raw 之外的全新 JSON/CSV 报告。")],
) -> None:
    """从原始存储复算全指标，不追加实验。"""
    try:
        _inside_project(output)
        report = write_minimal_report(raw, output)
    except (ValueError, OSError, JsonSchemaError, DocumentValidationError) as error:
        _failure(error)
    if not report.technical_gate_passed:
        raise typer.Exit(code=2)
    typer.echo(f"[通过] minimal report domain={report.domain} measurement_gate=true API=0")


def _inside_project(output: Path) -> None:
    root = Path.cwd()
    if not output.resolve().is_relative_to(root) or output.resolve() == root:
        raise ValueError("minimal_output_must_be_inside_project")


def _domain(value: str) -> MinimalDomain:
    if value == "scripted":
        return "scripted"
    if value == "fake_reference":
        return "fake_reference"
    raise ValueError("minimal_domain_invalid")


def _failure(error: ValueError | OSError | JsonSchemaError | DocumentValidationError) -> Never:
    # 只报告安全类型；Pydantic 错误可包含输入正文，不直接输出异常文本。
    typer.echo("[失败] minimal " + type(error).__name__ + "; existing evidence retained", err=True)
    raise typer.Exit(code=2) from error
