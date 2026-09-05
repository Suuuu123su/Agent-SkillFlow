"""T19 只读/离线命令组，不提供绕过可信宿主的Live入口。"""

import json
from pathlib import Path
from typing import Annotated

import typer

from skillflow.experiment.t19.delivery import export_all, recompute_all, save_check

app = typer.Typer(help="T19 冻结事实的离线导出、完整复算和比较。", no_args_is_help=True)


@app.command("export")
def export_command(
    phase: Annotated[Path, typer.Option(help="已完成的冻结阶段目录。")],
    campaign: Annotated[Path, typer.Option(help="实际核心与补证记录目录。")],
    live_root: Annotated[Path, typer.Option(help="仅用于读取费用账本。")],
    output: Annotated[Path, typer.Option(help="不存在的新导出目录。")],
) -> None:
    """删除原proof/report数值后导出，不读取密钥或API正文。"""
    export_all(phase, campaign, live_root, output)
    typer.echo("exported")


@app.command("recompute")
def recompute_command(
    source: Annotated[Path, typer.Option(help="脱敏事实导出目录。")],
    output: Annotated[Path, typer.Option(help="新的复算输出目录，不覆盖旧报告。")],
) -> None:
    """离线重建完整九类主结果与分层明细，无付费调用。"""
    result = recompute_all(source, output)
    typer.echo(
        json.dumps(
            {
                "data_status": result.data_status,
                "cores": result.completed_core,
                "audit_candidates": result.terminal_audit,
            }
        )
    )


@app.command("check")
def check_command(
    left: Annotated[Path, typer.Option(help="第一份独立复算目录。")],
    right: Annotated[Path, typer.Option(help="第二份独立复算目录。")],
    output: Annotated[Path, typer.Option(help="新的比对结果文件。")],
) -> None:
    """两个报告生成后才比较；不相等以非零退出码报告。"""
    result = save_check(left, right, output)
    typer.echo(json.dumps(result))
    if result["status"] != "passed":
        raise typer.Exit(1)


def register_t19_commands(parent: typer.Typer) -> None:
    """复用现有defense分组，不修改旧T18命令。"""
    parent.add_typer(app, name="t19")


if __name__ == "__main__":
    app()
