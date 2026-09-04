"""逐响应账本和逐阶段预算的纯计算，不读取模型正文。"""

from decimal import Decimal

from skillflow.experiment.t17.v2.api_models import ApiUsageEvent
from skillflow.experiment.t17.v2.campaign_models import StageProgress
from skillflow.experiment.t17.v2.run_models import (
    CoreTerminal,
    PhaseContract,
    ReplayTerminal,
    UnitUsage,
)
from skillflow.experiment.t17.v2.usage_summary import summarize_usage


def journal_totals(events: tuple[ApiUsageEvent, ...]) -> UnitUsage:
    """未知响应保留保守占用，已返回用量不重复累加。"""
    return summarize_usage(events)


def progress(
    phase: PhaseContract, cores: list[CoreTerminal], replays: list[ReplayTerminal]
) -> StageProgress:
    """进度来自已经写入的终态，不能把未运行单元当已评估。"""
    units: tuple[CoreTerminal | ReplayTerminal, ...] = (*cores, *replays)
    uses = tuple(u.usage for u in units)
    counts = {
        name: sum(getattr(u, name) for u in uses)
        for name in (
            "api_calls",
            "responses",
            "input_tokens",
            "cached_input_tokens",
            "cache_write_tokens",
            "output_tokens",
            "reasoning_tokens",
            "latency_ms",
        )
    }
    usage = UnitUsage(
        **counts,
        complete=all(u.complete for u in uses),
        estimated_cost_usd=sum((u.estimated_cost_usd for u in uses), Decimal(0)),
        reserved_cost_usd=sum((u.reserved_cost_usd for u in uses), Decimal(0)),
    )
    return StageProgress(
        stage=phase.stage,
        scheduled_core=phase.scheduled_core,
        scheduled_replay=phase.scheduled_replay,
        terminal_core=len(cores),
        terminal_replay=len(replays),
        failed_units=sum(u.status not in {"completed", "not_applicable"} for u in units),
        model_failures=sum(d.behavior != "normal" for u in units for d in u.decisions),
        usage=usage,
    )
