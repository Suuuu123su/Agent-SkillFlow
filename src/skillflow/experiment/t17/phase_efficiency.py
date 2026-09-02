"""T17 Phase 的逐单元效率统计与输入哈希清单。"""

from decimal import Decimal
from pathlib import Path

from skillflow.experiment.io import sha256_file
from skillflow.experiment.t16.live_record_builders import add_usage, zero_usage
from skillflow.experiment.t17.live_attempt_models import (
    T17LiveStageSummary,
    T17LiveUnitRecord,
)
from skillflow.experiment.t17.live_reference_client import ReferenceLiveTelemetry
from skillflow.experiment.t17.metric_models import T17EfficiencySummary
from skillflow.experiment.t17.metric_statistics import percentile


def build_efficiency_summary(
    records: tuple[T17LiveUnitRecord, ...],
    summary: T17LiveStageSummary,
) -> T17EfficiencySummary:
    """汇总 Step、调用、Token、延迟和费用的逐单元描述统计。"""
    if not records:
        return T17EfficiencySummary(
            unit_count=0,
            telemetry=summary.telemetry,
            agent_steps_mean=None,
            agent_steps_p95=None,
            api_calls_mean=None,
            api_calls_p95=None,
            latency_ms_mean=None,
            latency_ms_p95=None,
            estimated_cost_usd_mean=None,
            estimated_cost_usd_p95=None,
        )
    size = len(records)
    costs = tuple(float(item.telemetry.estimated_cost_usd) for item in records)
    cost_p95 = percentile(costs, 0.95)
    if cost_p95 is None:
        raise T17EfficiencyNarrowingError
    return T17EfficiencySummary(
        unit_count=size,
        telemetry=summary.telemetry,
        agent_steps_mean=sum(item.telemetry.agent_step_count for item in records) / size,
        agent_steps_p95=percentile(
            tuple(float(item.telemetry.agent_step_count) for item in records),
            0.95,
        ),
        api_calls_mean=sum(item.telemetry.api_call_count for item in records) / size,
        api_calls_p95=percentile(
            tuple(float(item.telemetry.api_call_count) for item in records),
            0.95,
        ),
        latency_ms_mean=sum(item.telemetry.latency_ms for item in records) / size,
        latency_ms_p95=percentile(
            tuple(float(item.telemetry.latency_ms) for item in records),
            0.95,
        ),
        estimated_cost_usd_mean=(
            sum(
                (item.telemetry.estimated_cost_usd for item in records),
                start=Decimal(0),
            )
            / size
        ),
        estimated_cost_usd_p95=Decimal(str(cost_p95)),
    )


def phase_source_hashes(
    attempt_root: Path,
    matrix_path: Path,
    registry_path: Path,
) -> dict[str, str]:
    """绑定 Phase 报告使用的 Raw、预检和静态输入。"""
    paths = {
        "live_summary": attempt_root / "live-summary.json",
        "trial_results": attempt_root / "trial-results.jsonl",
        "usage_journal": attempt_root / "actual-usage-journal.jsonl",
        "preflight": attempt_root / "preflight.json",
        "matrix": matrix_path,
        "scenario_registry": registry_path,
    }
    return {name: sha256_file(path) for name, path in paths.items()}


class T17EfficiencyNarrowingError(ValueError):
    """非空逐单元费用无法得到 p95。"""

    def __str__(self) -> str:
        """返回稳定 reason code。"""
        return "t17_efficiency_percentile_narrowing"


def aggregate_reference_telemetry(
    records: tuple[T17LiveUnitRecord, ...],
) -> ReferenceLiveTelemetry:
    """跨阶段/模式机械汇总实际用量与保守占用。"""
    usage = zero_usage()
    for item in records:
        usage = add_usage(usage, item.telemetry.token_usage)
    return ReferenceLiveTelemetry(
        api_call_count=sum(item.telemetry.api_call_count for item in records),
        response_count=sum(item.telemetry.response_count for item in records),
        agent_step_count=sum(item.telemetry.agent_step_count for item in records),
        retry_count=sum(item.telemetry.retry_count for item in records),
        refusal_count=sum(item.telemetry.refusal_count for item in records),
        no_call_count=sum(item.telemetry.no_call_count for item in records),
        token_usage=usage,
        latency_ms=sum(item.telemetry.latency_ms for item in records),
        estimated_cost_usd=sum(
            (item.telemetry.estimated_cost_usd for item in records),
            start=Decimal(0),
        ),
        conservative_reserved_usd=sum(
            (item.telemetry.conservative_reserved_usd for item in records),
            start=Decimal(0),
        ),
    )
