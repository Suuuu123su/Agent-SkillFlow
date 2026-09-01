"""两种模型共享的 Canary 运行合同与安全进度。"""

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from skillflow.experiment.t16.live_canary_usage_models import CanaryUsageJournalEvent
from skillflow.experiment.t16.live_config import T16CLiveConfig
from skillflow.experiment.t16.live_record_builders import add_usage, zero_usage
from skillflow.experiment.t16.live_usage_store import LiveTrialTerminalStatus
from skillflow.experiment.t16.provider import TokenUsage
from skillflow.experiment.t16.task_success_live_models import T16D2RawTrialRecord
from skillflow.experiment.t16.task_success_live_preflight import T16D2Environment
from skillflow.experiment.t16.task_success_live_run_support import (
    T16D2ProgressEvent,
    T16D2ProgressSink,
)
from skillflow.experiment.t16.trial import TrialResult

CANARY_COUNT = 11
OUTPUT_ROOT_NOT_EMPTY = "output_root 必须是不存在或为空的新 Canary Attempt 目录"


class T16D2CanaryRunError(RuntimeError):
    """Canary 新 Attempt 或冻结授权不满足执行条件。"""


@dataclass(frozen=True, slots=True)
class T16D2CanaryRunRequest:
    """一次全新 v3.1 Canary Attempt 的项目、输出与非秘密授权。"""

    project_root: Path
    output_root: Path
    environment: T16D2Environment


@dataclass(frozen=True, slots=True)
class CanaryRunContract:
    """单次 Canary 已冻结的配置与协议身份。"""

    config: T16CLiveConfig
    protocol_id: str
    provider_name: str = "openai"


def require_new_output(output: Path) -> None:
    """拒绝覆盖或续写任何既有 Attempt。"""
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise T16D2CanaryRunError(OUTPUT_ROOT_NOT_EMPTY)


def terminal_status(result: TrialResult) -> tuple[LiveTrialTerminalStatus, str | None]:
    """把 Trial 失败标记映射为持久化终态。"""
    if result.provider_error:
        return LiveTrialTerminalStatus.PARTIAL, "provider_error"
    if result.timeout:
        return LiveTrialTerminalStatus.PARTIAL, "timeout"
    if result.rate_limit:
        return LiveTrialTerminalStatus.PARTIAL, "rate_limit"
    return LiveTrialTerminalStatus.COMPLETED, None


def emit_canary_progress(
    progress: T16D2ProgressSink | None,
    records: tuple[T16D2RawTrialRecord, ...],
    terminal_events: tuple[CanaryUsageJournalEvent, ...],
    total_budget_usd: Decimal,
) -> None:
    """只发送计数、Token 与预算，不暴露模型输入或输出。"""
    if progress is None:
        return
    usage = zero_usage()
    for item in terminal_events:
        observed = item.observed_token_usage
        if isinstance(observed, TokenUsage):
            usage = add_usage(usage, observed)
    progress(
        T16D2ProgressEvent(
            observed=len(records),
            scheduled=CANARY_COUNT,
            infrastructure_invalid=sum(infrastructure_invalid(item) for item in records),
            api_calls=sum(item.api_call_count for item in terminal_events),
            total_tokens=(
                usage.input_tokens
                + usage.output_tokens
                + usage.reasoning_tokens
                + usage.cache_write_tokens
            ),
            conservative_reserved_usd=total_budget_usd,
        )
    )


def infrastructure_invalid(record: T16D2RawTrialRecord) -> bool:
    """识别计入 5% 停止门的基础设施失败。"""
    result = record.live_trial.result
    return result.timeout or result.rate_limit or result.provider_error
