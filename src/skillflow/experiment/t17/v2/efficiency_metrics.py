"""实际响应费用与失败请求保守占用分列，不把估算冒充账单。"""

from typing import TYPE_CHECKING

from skillflow.experiment.t17.v2.analysis_context import AnalysisGroup
from skillflow.experiment.t17.v2.measurements import measure
from skillflow.experiment.t17.v2.statistics_models import Measurement

if TYPE_CHECKING:
    from skillflow.experiment.t17.v2.run_models import CoreTerminal, ReplayTerminal


def efficiency_metrics(group: AnalysisGroup) -> dict[str, Measurement]:
    """保留全部核心与重放请求，包括拒绝、失败及未能完成的尝试。"""
    records: tuple[CoreTerminal | ReplayTerminal, ...] = (*group.cores, *group.replays)
    evidence = tuple(r.identity.unit_id for r in records) or group.evidence
    result = {}
    for name, field, unit in (
        ("actual_api_calls", "api_calls", "call_count"),
        ("actual_responses", "responses", "response_count"),
        ("input_tokens", "input_tokens", "token_count"),
        ("cached_input_tokens", "cached_input_tokens", "token_count"),
        ("cache_write_tokens", "cache_write_tokens", "token_count"),
        ("output_tokens", "output_tokens", "token_count"),
        ("reasoning_tokens", "reasoning_tokens", "token_count"),
        ("api_latency_ms", "latency_ms", "milliseconds"),
        ("estimated_cost_usd", "estimated_cost_usd", "usd_estimate_not_invoice"),
        ("conservative_reserved_usd", "reserved_cost_usd", "usd_reserved_not_invoice"),
    ):
        result[name] = measure(
            sum(float(getattr(r.usage, field)) for r in records),
            1,
            evidence,
            unit=unit,
            scope="core_and_replay_observed_usage",
            complete=all(r.usage.complete for r in records),
        )
    result["harness_latency_ms_mean"] = measure(
        sum(c.wall_latency_ms for c in group.cores),
        len(group.cores),
        group.evidence,
        unit="milliseconds",
        scope="core_wall_time_including_api",
        complete=group.complete,
    )
    result["unit_infrastructure_invalid"] = measure(
        sum(r.status == "infrastructure_invalid" for r in records),
        len(records),
        evidence,
        scope="core_and_replay_units",
    )
    result["unit_protocol_error"] = measure(
        sum(r.status == "protocol_error" for r in records),
        len(records),
        evidence,
        scope="core_and_replay_units",
    )
    result["unit_budget_exhausted"] = measure(
        sum(r.status == "budget_exhausted" for r in records),
        len(records),
        evidence,
        scope="core_and_replay_units",
    )
    return result
