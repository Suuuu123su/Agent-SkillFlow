"""T16-D.2 一次性秘密输入与安全进度 CLI。"""

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from skillflow.experiment.t16.httpx2_transport import managed_httpx2_transport
from skillflow.experiment.t16.live_cli import read_api_key
from skillflow.experiment.t16.openai_responses import OpenAIResponsesClient
from skillflow.experiment.t16.task_success_live_config import build_t16d2_live_config
from skillflow.experiment.t16.task_success_live_integrity import (
    build_t16d2_preflight_manifest,
)
from skillflow.experiment.t16.task_success_live_preflight import (
    load_t16d2_environment,
    load_t16d2_inputs,
)
from skillflow.experiment.t16.task_success_live_run import (
    T16D2ProgressEvent,
    T16D2ProgressSink,
    T16D2RunRequest,
    execute_t16d2_run,
)

ENVIRONMENT_NAMES = (
    "SKILLFLOW_PROVIDER",
    "SKILLFLOW_MODEL_ID",
    "SKILLFLOW_MAX_USD",
    "SKILLFLOW_LIVE_APPROVED",
)
OUTPUT_ROOT_NOT_EMPTY = "output_root 必须是不存在或为空的新 Attempt 目录"


class ConsoleProgress(T16D2ProgressSink):
    """只输出计数、失败、Token 与保守费用。"""

    def __call__(self, event: T16D2ProgressEvent) -> None:
        """输出一行脱敏阶段进度。"""
        typer.echo(
            f"[T16-D.2] {event.observed}/{event.scheduled}，"
            f"infra={event.infrastructure_invalid}，calls={event.api_calls}，"
            f"tokens={event.total_tokens}，"
            f"保守占用=${event.conservative_reserved_usd:.6f}"
        )


def main(
    project_root: Annotated[Path, typer.Option(exists=True, file_okay=False)],
    output_root: Annotated[Path, typer.Option(file_okay=False)],
) -> None:
    """先离线预检，再读取一次密钥并完成有界 48 条 bridge。"""
    root = project_root.resolve()
    output = output_root.resolve()
    environment = load_t16d2_environment(
        {name: os.environ.get(name, "") for name in ENVIRONMENT_NAMES}
    )
    inputs = load_t16d2_inputs(root)
    build_t16d2_live_config(root)
    build_t16d2_preflight_manifest(inputs, datetime.now(UTC))
    if output.exists() and any(output.iterdir()):
        raise typer.BadParameter(OUTPUT_ROOT_NOT_EMPTY)
    typer.echo("离线预检通过；现在只需输入一次 API Key，随后由同一进程有界复用。")
    api_key = read_api_key()
    with managed_httpx2_transport() as transport:
        summary = execute_t16d2_run(
            T16D2RunRequest(root, output, environment),
            OpenAIResponsesClient(api_key, transport),
            ConsoleProgress(),
        )
    del api_key
    typer.echo(
        f"T16-D.2 observed={summary.observed}/48，"
        f"infra={summary.infrastructure_invalid}，"
        f"估算费用=${summary.actual_estimated_cost_usd:.6f}，"
        f"stop={summary.stop_reason or 'none'}"
    )
    if not summary.final_gate_passed:
        raise typer.Exit(code=2)


if __name__ == "__main__":
    typer.run(main)
