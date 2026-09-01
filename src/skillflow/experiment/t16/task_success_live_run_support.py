"""T16-D.2 Runner 的停止、检查点、摘要与安全进度辅助。"""

import math
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Protocol

from skillflow.experiment.t16.budget import BudgetLedger
from skillflow.experiment.t16.live_record_builders import add_usage, zero_usage
from skillflow.experiment.t16.provider import TokenUsage
from skillflow.experiment.t16.task_success_live_integrity import sha256_file
from skillflow.experiment.t16.task_success_live_models import (
    T16D2Checkpoint,
    T16D2RawTrialRecord,
    T16D2RunSummary,
    T16D2StopReason,
)
from skillflow.experiment.t16.task_success_live_stage import scan_t16d2_secrets
from skillflow.experiment.t16.task_success_live_store import write_immutable_json

CHECKPOINT_COUNTS = frozenset({11, 23, 35, 47, 48})
CANARY_COUNT = 11
TRIAL_COUNT = 48
MAX_INFRASTRUCTURE_RATE = 0.05


@dataclass(frozen=True, slots=True)
class T16D2ProgressEvent:
    """只暴露计数、失败、Token 与预算的安全进度。"""

    observed: int
    scheduled: int
    infrastructure_invalid: int
    api_calls: int
    total_tokens: int
    conservative_reserved_usd: Decimal


class T16D2ProgressSink(Protocol):
    """允许 CLI 显示不含 Prompt、响应和凭据的进度。"""

    def __call__(self, event: T16D2ProgressEvent) -> None:
        """接收一条脱敏累计进度。"""
        ...


def check_immediate_stop(
    records: tuple[T16D2RawTrialRecord, ...],
    raw_path: Path,
    expected_model_revision: str = "gpt-5.6-luna",
) -> tuple[T16D2StopReason, str] | None:
    """检查一条落盘后必须立即终止的技术边界。"""
    revisions = {revision for item in records for revision in item.provider_model_revisions}
    if len(revisions) > 1 or any(item != expected_model_revision for item in revisions):
        return T16D2StopReason.MODEL_REVISION_CHANGED, "provider_model_revision_changed"
    infrastructure = sum(_infrastructure_invalid(item) for item in records)
    if infrastructure / len(records) > MAX_INFRASTRUCTURE_RATE:
        return T16D2StopReason.INFRASTRUCTURE_RATE, "infrastructure_invalid_above_5_percent"
    if any(
        item.live_trial.task_success_result is not None
        and item.live_trial.task_success_result.not_evaluable_assertion_ids
        for item in records
    ):
        return T16D2StopReason.TECHNICAL_NOT_EVALUABLE, "required_assertion_not_evaluable"
    if not scan_t16d2_secrets(raw_path):
        return T16D2StopReason.SECRET_SCAN, "secret_pattern_detected"
    return None


def predicted_total_usd(
    records: tuple[T16D2RawTrialRecord, ...],
    budget: BudgetLedger,
    remaining: int,
) -> Decimal:
    """使用已观察单链费用的 P95 预测完整阶段总费用。"""
    costs = sorted(item.live_trial.result.estimated_cost_usd for item in records)
    if not costs:
        return budget.total_spent_usd
    index = max(0, math.ceil(len(costs) * 0.95) - 1)
    return budget.total_spent_usd + costs[index] * remaining


def write_checkpoint(
    output: Path,
    records: tuple[T16D2RawTrialRecord, ...],
    budget: BudgetLedger,
    created_at: datetime,
    raw_path: Path,
) -> None:
    """写入一个不可变累计检查点。"""
    checkpoint = T16D2Checkpoint(
        created_at=created_at,
        observed=len(records),
        conservative_reserved_usd=budget.total_spent_usd,
        actual_estimated_cost_usd=sum(
            (item.live_trial.result.estimated_cost_usd for item in records),
            start=Decimal(0),
        ),
        token_usage=_token_usage(records),
        raw_records_sha256=sha256_file(raw_path),
    )
    write_immutable_json(output / f"checkpoint-{len(records):03d}.json", checkpoint)


def build_run_summary(  # noqa: PLR0913, PLR0917
    records: tuple[T16D2RawTrialRecord, ...],
    budget: BudgetLedger,
    created_at: datetime,
    raw_path: Path,
    canary_gate_passed: bool,
    final_gate_passed: bool,
    stop_reason: T16D2StopReason | None,
    stop_detail: str | None,
) -> T16D2RunSummary:
    """从已保存记录机械构造阶段摘要。"""
    return T16D2RunSummary(
        created_at=created_at,
        observed=len(records),
        unrun=TRIAL_COUNT - len(records),
        canary_observed=min(CANARY_COUNT, len(records)),
        canary_gate_passed=canary_gate_passed,
        final_gate_passed=final_gate_passed,
        stop_reason=stop_reason,
        stop_detail=stop_detail,
        infrastructure_invalid=sum(_infrastructure_invalid(item) for item in records),
        conservative_reserved_usd=budget.total_spent_usd,
        actual_estimated_cost_usd=sum(
            (item.live_trial.result.estimated_cost_usd for item in records),
            start=Decimal(0),
        ),
        token_usage=_token_usage(records),
        api_call_count=sum(item.live_trial.result.api_call_count for item in records),
        raw_records_sha256=sha256_file(raw_path),
    )


def emit_progress(
    progress: T16D2ProgressSink | None,
    records: tuple[T16D2RawTrialRecord, ...],
    budget: BudgetLedger,
) -> None:
    """只向可选观察者发送脱敏累计计数。"""
    if progress is None:
        return
    usage = _token_usage(records)
    progress(
        T16D2ProgressEvent(
            observed=len(records),
            scheduled=TRIAL_COUNT,
            infrastructure_invalid=sum(_infrastructure_invalid(item) for item in records),
            api_calls=sum(item.live_trial.result.api_call_count for item in records),
            total_tokens=(
                usage.input_tokens
                + usage.output_tokens
                + usage.reasoning_tokens
                + usage.cache_write_tokens
            ),
            conservative_reserved_usd=budget.total_spent_usd,
        )
    )


def _token_usage(records: tuple[T16D2RawTrialRecord, ...]) -> TokenUsage:
    usage = zero_usage()
    for item in records:
        usage = add_usage(usage, item.live_trial.result.token_usage)
    return usage


def _infrastructure_invalid(record: T16D2RawTrialRecord) -> bool:
    result = record.live_trial.result
    return result.timeout or result.rate_limit or result.provider_error
