"""中文监督入口：费用先批准，父进程持钥，子进程执行实验。"""

from contextlib import suppress
from pathlib import Path
from typing import Annotated

import typer

from skillflow.experiment.t17.v2.campaign import read_campaign_key
from skillflow.experiment.t17.v2.campaign_models import StageProgress
from skillflow.experiment.t17.v2.campaign_setup import CampaignSetup, prepare_campaign
from skillflow.experiment.t17.v2.cost_plan import write_cost_plan
from skillflow.experiment.t17.v2.keeper_session import create_session_control, run_key_session
from skillflow.experiment.t17.v2.key_keeper import MemoryKeyKeeper


def cost_plan_command(
    protocol: Annotated[Path, typer.Option(exists=True, file_okay=False)],
    readiness: Annotated[Path, typer.Option(exists=True, file_okay=False)],
    output: Annotated[Path, typer.Option(help="尚不存在的总费用计划文件。")],
) -> None:
    """核对全部离线证据并申请一次总额，不核价、不访问 API。"""
    try:
        plan = write_cost_plan(Path.cwd(), protocol, readiness, output)
    except (ValueError, OSError) as error:
        typer.echo("[失败] 费用计划 " + type(error).__name__, err=True)
        raise typer.Exit(code=2) from error
    typer.echo(f"[待批准] 总上限 ${plan.requested_max_total_usd}；API=0；未授予调用权限")


def live_command(
    protocol: Annotated[Path, typer.Option(exists=True, file_okay=False)],
    cost_plan: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    approval: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    output: Annotated[Path, typer.Option(help="全新的监督执行目录。")],
) -> None:
    """先读明确金额批准，再隐藏输入一次密钥；只依次执行 E、F、G、H。"""
    try:
        prepared = prepare_campaign(
            CampaignSetup(Path.cwd(), output, protocol, cost_plan, approval)
        )
        control = create_session_control(Path.cwd(), output)
        _notice("保钥控制目录：" + control.relative_to(Path.cwd()).as_posix())
        secret = read_campaign_key()
        result = run_key_session(prepared, MemoryKeyKeeper(secret), _progress, _notice, control)
    except (ValueError, OSError, KeyboardInterrupt) as error:
        typer.echo("[停止] 监督执行 " + type(error).__name__ + "；已有证据保留", err=True)
        raise typer.Exit(code=2) from error
    if result is None:
        _notice("已按指令结束保钥；原始记录保留，实验不标为完成。")
        raise typer.Exit(code=2)
    typer.echo(
        f"阶段结束={len(result.stages)} 全部阶段完成={result.all_stages_finished} "
        f"已返回费用估算=${result.estimated_cost_usd} 保守占用=${result.reserved_cost_usd}"
    )
    if not result.all_stages_finished:
        raise typer.Exit(code=2)


def _progress(value: StageProgress) -> None:
    usage = value.usage
    _notice(
        f"{value.stage.value} 任务={value.terminal_core}/{value.scheduled_core} "
        f"重放={value.terminal_replay}/{value.scheduled_replay} 未完成={value.failed_units} "
        f"模型失败={value.model_failures} 请求={usage.api_calls} "
        f"输入/输出/推理 Token={usage.input_tokens}/{usage.output_tokens}/{usage.reasoning_tokens} "
        f"估算=${usage.estimated_cost_usd} 保守占用=${usage.reserved_cost_usd}"
    )


def _notice(message: str) -> None:
    with suppress(OSError, UnicodeError, ValueError):
        typer.echo(message)
