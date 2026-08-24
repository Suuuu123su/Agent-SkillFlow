"""SkillFlow 命令行入口。"""

import platform
import sqlite3
import tempfile
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Annotated, Final

import typer

from skillflow import __version__

app: Final = typer.Typer(
    help="SkillFlow：Agent Skill 安全传播测量原型。",
    no_args_is_help=True,
)
MINIMUM_PYTHON: Final = (3, 11)
RUNTIME_DISTRIBUTIONS: Final = (
    "jsonschema",
    "networkx",
    "pydantic",
    "PyYAML",
    "typer",
)


@dataclass(frozen=True, slots=True)
class DoctorCheck:
    """一次环境检查的不可变结果。"""

    name: str
    passed: bool
    detail: str


def collect_doctor_checks(temp_dir: Path) -> tuple[DoctorCheck, ...]:
    """收集离线环境检查结果。"""
    python_version = platform.python_version()
    python_supported = tuple(map(int, python_version.split(".")[:2])) >= MINIMUM_PYTHON

    versions: list[str] = []
    missing: list[str] = []
    for distribution in RUNTIME_DISTRIBUTIONS:
        try:
            versions.append(f"{distribution}={metadata.version(distribution)}")
        except metadata.PackageNotFoundError:
            missing.append(distribution)

    dependency_check = DoctorCheck(
        name="依赖包",
        passed=not missing,
        detail=(f"已安装：{', '.join(versions)}" if not missing else f"缺少：{', '.join(missing)}"),
    )

    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=temp_dir,
            prefix="skillflow-doctor-",
            delete=True,
        ) as probe:
            probe.write(b"skillflow")
            probe.flush()
        temp_check = DoctorCheck(
            name="临时目录",
            passed=True,
            detail=f"可写：{temp_dir}",
        )
    except OSError as error:
        reason = error.strerror if error.strerror is not None else error.__class__.__name__
        temp_check = DoctorCheck(
            name="临时目录",
            passed=False,
            detail=f"不可写或不可用：{reason}",
        )

    return (
        DoctorCheck(
            name="Python",
            passed=python_supported,
            detail=f"{python_version}（要求 >=3.11）",
        ),
        DoctorCheck(
            name="SQLite",
            passed=True,
            detail=sqlite3.sqlite_version,
        ),
        dependency_check,
        temp_check,
    )


@app.command("version")
def version_command() -> None:
    """输出 SkillFlow 版本。"""
    typer.echo(f"SkillFlow {__version__}")


@app.command()
def doctor(
    temp_dir: Annotated[
        Path | None,
        typer.Option(help="用于可写性检查的临时目录；默认使用系统临时目录。"),
    ] = None,
) -> None:
    """离线检查 Python、SQLite、依赖包和临时目录。"""
    selected_temp_dir = temp_dir if temp_dir is not None else Path(tempfile.gettempdir())
    checks = collect_doctor_checks(selected_temp_dir)
    for check in checks:
        marker = "[通过]" if check.passed else "[失败]"
        typer.echo(f"{marker} {check.name}: {check.detail}")

    if not all(check.passed for check in checks):
        raise typer.Exit(code=1)


def main() -> None:
    """运行命令行应用。"""
    app()


if __name__ == "__main__":
    main()
