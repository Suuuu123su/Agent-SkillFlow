"""响应账本的统一聚合：已返回下界、未知用量和保守占用不能混淆。"""

from decimal import Decimal

from skillflow.experiment.t17.v2.api_models import ApiUsageEvent
from skillflow.experiment.t17.v2.run_models import UnitUsage


def summarize_usage(
    events: tuple[ApiUsageEvent, ...], *, reserved: Decimal | None = None
) -> UnitUsage:
    """逐单元和逐阶段使用相同的请求闭合规则；重试不能抹掉前次未知用量。"""
    pending: dict[tuple[str, int], str] = {}
    for event in events:
        key = (event.unit_id, event.attempt_index)
        if event.event_type == "attempt":
            pending[key] = "unclosed_attempt"
        elif event.event_type == "response":
            pending[key] = "response_settlement_missing"
        elif event.event_type == "settlement":
            pending.pop(key, None)
        elif event.event_type in {"transport_failure", "http_error"}:
            pending[key] = event.reason or "response_usage_missing"
    responses = tuple(e for e in events if e.event_type == "response")
    usages = tuple(e.usage for e in responses if e.usage is not None)
    return UnitUsage(
        complete=not pending,
        missing_reason=next(iter(pending.values()), None),
        api_calls=sum(e.event_type == "attempt" for e in events),
        responses=len(responses),
        input_tokens=sum(u.input_tokens for u in usages),
        cached_input_tokens=sum(u.cached_input_tokens for u in usages),
        cache_write_tokens=sum(u.cache_write_tokens for u in usages),
        output_tokens=sum(u.output_tokens for u in usages),
        reasoning_tokens=sum(u.reasoning_tokens for u in usages),
        latency_ms=sum(e.latency_ms or 0 for e in events),
        estimated_cost_usd=sum((e.estimated_cost_usd or Decimal(0) for e in responses), Decimal(0)),
        reserved_cost_usd=(events[-1].total_reserved_usd if events else Decimal(0))
        if reserved is None
        else reserved,
        response_ids=tuple(e.response_id for e in responses if e.response_id is not None),
    )
