"""从公开Token记录和冻结价格独立计费；费用为估算而非供应商账单。"""

from collections import Counter
from decimal import Decimal

from skillflow.experiment.t16.provider import PricingRates, estimate_result_cost
from skillflow.experiment.t17.v2.api_models import ApiUsageEvent
from skillflow.experiment.t17.v2.journal import _hash_event
from skillflow.experiment.t17.v2.run_models import UnitUsage
from skillflow.experiment.t17.v2.usage_summary import summarize_usage
from skillflow.models.base import StrictModel


class LedgerInputs(StrictModel):
    """原哈希链逐本导出；已有估算字段仅用于比对，从不充作复算结果。"""

    pricing: PricingRates
    journals: dict[str, tuple[ApiUsageEvent, ...]]


class CostReport(StrictModel):
    """分阶段、核心/审计和每个调用保留原始项。"""

    complete: bool
    api_calls: int
    responses: int
    estimated_cost_usd: Decimal
    reserved_cost_usd: Decimal
    usage_by_attempt: dict[str, UnitUsage]
    cost_by_call: dict[str, Decimal]
    counts: dict[str, int]


def recompute_cost(inputs: LedgerInputs) -> CostReport:
    """保留未知预留；同一响应ID不可跨日志重复使用。"""
    usages = {}
    costs = {}
    counts: Counter[str] = Counter()
    ids: set[str] = set()
    for name, rows in inputs.journals.items():
        previous = None
        for sequence, event in enumerate(rows, start=1):
            if (
                event.sequence != sequence
                or event.previous_sha256 != previous
                or event.event_sha256 != _hash_event(event)
            ):
                raise ValueError("t19_public_ledger_hash")
            previous = event.event_sha256
            counts[event.event_type] += 1
            if event.response_status:
                counts["provider_status." + event.response_status] += 1
            if event.event_type == "response":
                if event.usage is None or event.response_id is None or event.response_id in ids:
                    raise ValueError("t19_public_response_binding")
                ids.add(event.response_id)
                value = estimate_result_cost(inputs.pricing, event.usage)
                costs[name + ":" + str(event.attempt_index)] = value
                if value != event.estimated_cost_usd:
                    raise ValueError("t19_cost_from_tokens_mismatch")
        usages[name] = summarize_usage(rows)
    return CostReport(
        complete=all(u.complete for u in usages.values()),
        api_calls=counts["attempt"],
        responses=counts["response"],
        estimated_cost_usd=sum(costs.values(), Decimal()),
        reserved_cost_usd=max((u.reserved_cost_usd for u in usages.values()), default=Decimal()),
        usage_by_attempt=usages,
        cost_by_call=costs,
        counts=dict(counts),
    )
