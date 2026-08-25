"""T15 OpenClaw Pilot 命令行入口。"""

import shutil
from pathlib import Path
from typing import Annotated, Never

import typer

from skillflow.pilot.errors import OpenClawPilotError, PilotRunError
from skillflow.pilot.runner import PilotRunRequest, execute_t15_pilot

app = typer.Typer(help="运行 T15 Mock/OpenClaw 双 Adapter Pilot。")


@app.command()
def run(
    openclaw_root: Annotated[Path, typer.Option(help="固定 revision 的 OpenClaw checkout。")],
    output: Annotated[Path, typer.Option(help="必须尚不存在的 Pilot 输出目录。")],
    project_root: Annotated[
        Path | None, typer.Option(help="Agent-SkillFlow 仓库根目录；默认当前目录。")
    ] = None,
) -> None:
    """在隔离本地 Gateway 中运行 B0、G0、M2。"""
    node = _executable("node")
    git = _executable("git")
    selected_project_root = Path.cwd() if project_root is None else project_root
    try:
        report = execute_t15_pilot(
            PilotRunRequest(
                project_root=selected_project_root.resolve(),
                openclaw_root=openclaw_root.resolve(),
                output_root=output.resolve(),
                node_path=node,
                git_path=git,
            )
        )
    except (OpenClawPilotError, PilotRunError) as error:
        _failure(error)
    typer.echo(f"[通过] T15 Pilot 场景={len(report.comparisons)} OpenClaw={report.openclaw_commit}")


def _executable(name: str) -> Path:
    path = shutil.which(name)
    if path is None:
        raise PilotRunError.executable_missing(name)
    return Path(path)


def _failure(error: Exception) -> Never:
    typer.echo(f"[失败] {error}", err=True)
    raise typer.Exit(code=1) from error


def main() -> None:
    """运行 T15 Pilot CLI。"""
    app()


if __name__ == "__main__":
    main()
