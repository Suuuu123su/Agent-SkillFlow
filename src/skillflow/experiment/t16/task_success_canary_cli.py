"""T16-D.2 v3.1 Canary 的一次性秘密输入与安全进度 CLI。"""

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from skillflow.experiment.t16.httpx2_transport import managed_httpx2_transport
from skillflow.experiment.t16.live_cli import read_api_key
from skillflow.experiment.t16.openai_responses import OpenAIResponsesClient
from skillflow.experiment.t16.t16e_integrity import load_t16e_model1_baseline
from skillflow.experiment.t16.task_success_canary_preflight import (
    load_t16d2r_canary_environment,
    load_t16d2r_canary_inputs,
    load_t16e_environment,
)
from skillflow.experiment.t16.task_success_canary_run import (
    OUTPUT_ROOT_NOT_EMPTY,
    T16D2CanaryRunRequest,
    execute_t16d2r_canary_run,
    execute_t16e_canary_run,
)
from skillflow.experiment.t16.task_success_live_config import (
    build_t16d2r_canary_config,
    build_t16e_canary_config,
)
from skillflow.experiment.t16.task_success_live_integrity import (
    build_t16d2r_preflight_manifest,
)
from skillflow.experiment.t16.task_success_live_run_support import (
    T16D2ProgressEvent,
    T16D2ProgressSink,
)

ENVIRONMENT_NAMES = (
    "SKILLFLOW_PROVIDER",
    "SKILLFLOW_MODEL_ID",
    "SKILLFLOW_MAX_USD",
    "SKILLFLOW_LIVE_APPROVED",
)
T16E_ENVIRONMENT_NAMES = (
    "SKILLFLOW_SECOND_PROVIDER",
    "SKILLFLOW_SECOND_MODEL_ID",
    "SKILLFLOW_MAX_USD",
    "SKILLFLOW_LIVE_APPROVED",
)


class CanaryConsoleProgress(T16D2ProgressSink):
    """只输出计数、基础设施失败、Token 与保守费用。"""

    def __call__(self, event: T16D2ProgressEvent) -> None:
        """输出一行不含 Prompt、响应和凭据的进度。"""
        typer.echo(
            f"[T16-D.2 v3.1 Canary] {event.observed}/{event.scheduled}，"
            f"infra={event.infrastructure_invalid}，calls={event.api_calls}，"
            f"tokens={event.total_tokens}，"
            f"保守占用=${event.conservative_reserved_usd:.6f}"
        )


class T16EConsoleProgress(T16D2ProgressSink):
    """第二模型只输出安全计数、Token 与当前预算占用。"""

    def __call__(self, event: T16D2ProgressEvent) -> None:
        """输出一行不含 Prompt、响应或凭据的进度。"""
        typer.echo(
            f"[T16-E Model2] {event.observed}/{event.scheduled}，"
            f"infra={event.infrastructure_invalid}，calls={event.api_calls}，"
            f"tokens={event.total_tokens}，budget=${event.conservative_reserved_usd:.6f}"
        )


def main(
    project_root: Annotated[Path, typer.Option(exists=True, file_okay=False)],
    output_root: Annotated[Path, typer.Option(file_okay=False)],
) -> None:
    """离线复核后读取一次密钥，并且只运行冻结的 11 条 Canary。"""
    root = project_root.resolve()
    output = output_root.resolve()
    environment = load_t16d2r_canary_environment(
        {name: os.environ.get(name, "") for name in ENVIRONMENT_NAMES}
    )
    prepared = load_t16d2r_canary_inputs(root)
    config = build_t16d2r_canary_config(root)
    build_t16d2r_preflight_manifest(prepared.inputs, config, datetime.now(UTC))
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise typer.BadParameter(OUTPUT_ROOT_NOT_EMPTY)
    typer.echo("离线预检通过；请输入一次 API Key。本进程会在 11 条内有界复用。")
    api_key = read_api_key()
    try:
        with managed_httpx2_transport() as transport:
            summary = execute_t16d2r_canary_run(
                T16D2CanaryRunRequest(root, output, environment),
                OpenAIResponsesClient(api_key, transport),
                CanaryConsoleProgress(),
            )
    finally:
        del api_key
    actual_cost = (
        "N/A"
        if summary.observed_estimated_cost_usd is None
        else f"${summary.observed_estimated_cost_usd:.6f}"
    )
    typer.echo(
        f"T16-D.2 v3.1 Canary observed={summary.observed}/11，"
        f"infra={summary.infrastructure_invalid}，actual_cost={actual_cost}，"
        f"reserved=${summary.conservative_reserved_usd:.6f}，"
        f"status={summary.status}"
    )
    if summary.status != "PASSED":
        raise typer.Exit(code=2)


def main_t16e(
    project_root: Annotated[Path, typer.Option(exists=True, file_okay=False)],
    output_root: Annotated[Path, typer.Option(file_okay=False)],
) -> None:
    """离线复核第二模型合同后读取一次不同的 API Key。"""
    root = project_root.resolve()
    output = output_root.resolve()
    environment = load_t16e_environment(
        {name: os.environ.get(name, "") for name in T16E_ENVIRONMENT_NAMES}
    )
    prepared = load_t16d2r_canary_inputs(root)
    config = build_t16e_canary_config(root)
    build_t16d2r_preflight_manifest(prepared.inputs, config, datetime.now(UTC))
    load_t16e_model1_baseline(root)
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise typer.BadParameter(OUTPUT_ROOT_NOT_EMPTY)
    typer.echo("T16-E 离线预检通过；请输入另一把 OpenAI API Key，仅在本进程复用一次。")
    api_key = read_api_key()
    try:
        with managed_httpx2_transport() as transport:
            summary = execute_t16e_canary_run(
                T16D2CanaryRunRequest(root, output, environment),
                OpenAIResponsesClient(api_key, transport),
                T16EConsoleProgress(),
            )
    finally:
        del api_key
    actual_cost = (
        "N/A"
        if summary.observed_estimated_cost_usd is None
        else f"${summary.observed_estimated_cost_usd:.6f}"
    )
    typer.echo(
        f"T16-E Model2 observed={summary.observed}/11，"
        f"infra={summary.infrastructure_invalid}，actual_cost={actual_cost}，"
        f"budget=${summary.conservative_reserved_usd:.6f}，status={summary.status}"
    )
    if summary.status != "PASSED":
        raise typer.Exit(code=2)


if __name__ == "__main__":
    typer.run(main)
