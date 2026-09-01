"""T16-C 交互式真实模型入口；凭据只从不可见终端输入读取。"""

import getpass
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Protocol

import typer
from pydantic import SecretStr

from skillflow.experiment.t16.httpx2_transport import managed_httpx2_transport
from skillflow.experiment.t16.live_campaign_report import load_or_create_live_reanalysis_v4
from skillflow.experiment.t16.live_config import load_t16c_config
from skillflow.experiment.t16.live_reanalysis_v3 import LiveReanalysisPaths
from skillflow.experiment.t16.live_reanalysis_v4_models import LiveReanalysisReportV4
from skillflow.experiment.t16.live_run import (
    LivePhaseRequest,
    LiveProgressEvent,
    LiveProgressSink,
    execute_live_phase,
)
from skillflow.experiment.t16.live_run_models import LivePhase, LivePhaseSummary
from skillflow.experiment.t16.openai_responses import OpenAIResponsesClient

API_KEY_PROMPT = "请输入新的 OpenAI API Key（输入不可见）："
HTTP_SERVER_ERROR_MIN = 500
SMOKE_BACKOFF_BASE_SECONDS = 5.0
SMOKE_BACKOFF_MAX_SECONDS = 10.0


class SecretReader(Protocol):
    """允许测试替换不可见终端输入。"""

    def __call__(self, prompt: str) -> str:
        """读取一次终端秘密。"""
        ...


class SupervisedAttemptRunner(Protocol):
    """主管进程可注入的单次 Campaign 边界。"""

    def __call__(
        self,
        attempt_root: Path,
        api_key: SecretStr,
        initial_total_reserved_usd: Decimal,
    ) -> "LiveCampaignResult":
        """使用同一个内存密钥执行一次不可变尝试。"""
        ...


class Sleeper(Protocol):
    """允许测试跳过有界退避。"""

    def __call__(self, seconds: float) -> None:
        """等待指定秒数。"""
        ...


@dataclass(frozen=True, slots=True)
class EmptyApiKeyError(ValueError):
    """用户没有在安全终端提供新密钥。"""

    def __str__(self) -> str:
        """返回不含凭据的稳定错误。"""
        return "没有输入 API Key"


@dataclass(frozen=True, slots=True)
class LiveCampaignResult:
    """Smoke 与可选完整矩阵的阶段摘要。"""

    smoke: LivePhaseSummary
    model1: LivePhaseSummary | None
    metrics: LiveReanalysisReportV4 | None


@dataclass(frozen=True, slots=True)
class LiveCampaignRequest:
    """一次 Campaign 的路径、恢复状态与累计保守预算。"""

    project_root: Path
    output_root: Path
    resume: bool = False
    initial_total_reserved_usd: Decimal = Decimal(0)


@dataclass(frozen=True, slots=True)
class SupervisedCampaignRequest:
    """一次输入主管进程的项目与不可变尝试根目录。"""

    project_root: Path
    output_root: Path


@dataclass(frozen=True, slots=True)
class SupervisedCampaignResult:
    """同一内存密钥下的有界不可变尝试序列。"""

    attempts: tuple[LiveCampaignResult, ...]
    final: LiveCampaignResult
    final_attempt_root: Path


class ConsoleProgress(LiveProgressSink):
    """只显示计数和保守预算，不显示模型输入输出。"""

    def __call__(self, event: LiveProgressEvent) -> None:
        """输出一行可供 Codex 终端轮询的安全进度。"""
        typer.echo(
            f"[{event.phase.value}] {event.completed}/{event.expected}，"
            f"保守占用 ${event.conservative_reserved_usd:.6f}"
        )


def read_api_key(reader: SecretReader | None = None) -> SecretStr:
    """只从不可见交互输入读取密钥；没有环境变量或文件回退。"""
    raw = (reader or getpass.getpass)(API_KEY_PROMPT)
    if not raw:
        raise EmptyApiKeyError
    secret = SecretStr(raw)
    del raw
    return secret


def run_live_campaign(
    request: LiveCampaignRequest,
    api_key: SecretStr,
    progress: LiveProgressSink | None = None,
) -> LiveCampaignResult:
    """在同一受控连接中先跑 48 条 Smoke，通过后才跑 360 条。"""
    with managed_httpx2_transport() as transport:
        client = OpenAIResponsesClient(api_key, transport)
        smoke = execute_live_phase(
            LivePhaseRequest(
                project_root=request.project_root,
                output_root=request.output_root / LivePhase.SMOKE.value,
                phase=LivePhase.SMOKE,
                resume=request.resume,
                initial_total_reserved_usd=request.initial_total_reserved_usd,
            ),
            client,
            progress,
        )
        if not smoke.live_gate_passed:
            return LiveCampaignResult(smoke, None, None)
        model1 = execute_live_phase(
            LivePhaseRequest(
                project_root=request.project_root,
                output_root=request.output_root / LivePhase.MODEL1.value,
                phase=LivePhase.MODEL1,
                resume=request.resume,
                initial_total_reserved_usd=smoke.conservative_reserved_usd,
            ),
            client,
            progress,
        )
    if not model1.live_gate_passed:
        return LiveCampaignResult(smoke, model1, None)
    model1_root = request.output_root / LivePhase.MODEL1.value
    t16_root = request.project_root / "experiments" / "t16"
    metrics = load_or_create_live_reanalysis_v4(
        LiveReanalysisPaths(
            source_path=model1_root / "trial-results.jsonl",
            output_path=model1_root / "metrics-reanalysis-v0.4.json",
            preregistration_path=t16_root / "preregistration_t16c_v2.yaml",
            matrix_path=t16_root / "matrix_model1_t16c_v2.yaml",
        ),
        resume=request.resume,
    )
    return LiveCampaignResult(smoke, model1, metrics)


def run_supervised_campaign(
    request: SupervisedCampaignRequest,
    api_key: SecretStr,
    progress: LiveProgressSink | None = None,
    attempt_runner: SupervisedAttemptRunner | None = None,
    sleep: Sleeper | None = None,
) -> SupervisedCampaignResult:
    """一次读取密钥；Smoke 瞬态失败最多执行三次不可变尝试。"""
    config = load_t16c_config(request.project_root / "experiments" / "t16" / "t16c_live.yaml")

    def default_runner(
        attempt_root: Path,
        secret: SecretStr,
        initial_reserved: Decimal,
    ) -> LiveCampaignResult:
        return run_live_campaign(
            LiveCampaignRequest(
                project_root=request.project_root,
                output_root=attempt_root,
                initial_total_reserved_usd=initial_reserved,
            ),
            secret,
            progress,
        )

    runner = attempt_runner or default_runner
    sleeper = sleep or time.sleep
    attempts: list[LiveCampaignResult] = []
    total_reserved = Decimal(0)
    for attempt_index in range(1, config.max_smoke_attempts + 1):
        attempt_root = request.output_root / f"attempt-{attempt_index:02d}"
        result = runner(attempt_root, api_key, total_reserved)
        attempts.append(result)
        if result.model1 is not None or not _retryable_smoke_failure(result.smoke):
            return SupervisedCampaignResult(tuple(attempts), result, attempt_root)
        if attempt_index == config.max_smoke_attempts:
            return SupervisedCampaignResult(tuple(attempts), result, attempt_root)
        total_reserved = result.smoke.conservative_reserved_usd
        typer.echo(
            f"[supervisor] Smoke 瞬态失败，保留 attempt-{attempt_index:02d}；"
            "同一内存密钥将在有界退避后重试。"
        )
        sleeper(
            min(
                SMOKE_BACKOFF_BASE_SECONDS * attempt_index,
                SMOKE_BACKOFF_MAX_SECONDS,
            )
        )
    raise AssertionError


def _retryable_smoke_failure(summary: LivePhaseSummary) -> bool:
    detail = summary.stop_detail or ""
    if detail in {"timeout", "rate_limit"}:
        return True
    if not detail.startswith("provider_error"):
        return False
    status = next(
        (
            int(item.removeprefix("status="))
            for item in detail.split(":")
            if item.startswith("status=") and item.removeprefix("status=").isdigit()
        ),
        None,
    )
    return status is None or status >= HTTP_SERVER_ERROR_MIN


def main(
    project_root: Annotated[Path, typer.Option(exists=True, file_okay=False)],
    output_root: Annotated[Path, typer.Option(file_okay=False)],
    resume: Annotated[bool, typer.Option()] = False,
) -> None:
    """安全读取一次密钥，并执行有硬预算的 T16-C。"""
    api_key = read_api_key()
    if resume:
        campaign = run_live_campaign(
            LiveCampaignRequest(
                project_root=project_root.resolve(),
                output_root=output_root.resolve(),
                resume=True,
            ),
            api_key,
            ConsoleProgress(),
        )
    else:
        campaign = run_supervised_campaign(
            SupervisedCampaignRequest(
                project_root=project_root.resolve(),
                output_root=output_root.resolve(),
            ),
            api_key,
            ConsoleProgress(),
        ).final
    del api_key
    typer.echo(campaign.smoke.model_dump_json())
    if campaign.model1 is None:
        raise typer.Exit(code=2)
    typer.echo(campaign.model1.model_dump_json())
    if not campaign.model1.live_gate_passed:
        raise typer.Exit(code=2)
    if campaign.metrics is None:
        raise typer.Exit(code=2)
    typer.echo(campaign.metrics.model_dump_json())


if __name__ == "__main__":
    typer.run(main)
