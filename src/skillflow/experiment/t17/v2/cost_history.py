"""只读历史累计日志，先差分再估算每个实际响应，禁止重复累加。"""

import math
from decimal import Decimal
from pathlib import Path

from skillflow.experiment.t16.provider import PricingRates, TokenUsage, estimate_result_cost
from skillflow.experiment.t17.live_journal import load_live_journal
from skillflow.experiment.t17.v2.cost_models import HistoricalUsage
from skillflow.experiment.t17.v2.frozen import file_digest


def historical_usage(root: Path, path: Path) -> tuple[HistoricalUsage, tuple[TokenUsage, ...]]:
    """费用来源有哈希，旧延迟缺失不冒充新版延迟实测。"""
    events = load_live_journal(path)
    previous: dict[str, TokenUsage] = {}
    samples = []
    latest_cost: dict[str, Decimal] = {}
    zero = TokenUsage(input_tokens=0, cached_input_tokens=0, output_tokens=0, reasoning_tokens=0)
    for event in events:
        usage = event.observed_token_usage
        if event.event_type != "response" or usage is None:
            continue
        last = previous.get(event.unit_id, zero)
        sample = TokenUsage.model_validate(
            {name: getattr(usage, name) - getattr(last, name) for name in TokenUsage.model_fields}
        )
        samples.append(sample)
        previous[event.unit_id] = usage
        latest_cost[event.unit_id] = event.observed_estimated_cost_usd or Decimal(0)
    if not samples:
        raise ValueError("v2_cost_history_without_responses")
    return HistoricalUsage(
        source_path=path.resolve().relative_to(root.resolve()).as_posix(),
        source_file=file_digest(path),
        observed_responses=len(samples),
        observed_input_tokens=sum(s.input_tokens for s in samples),
        observed_generated_tokens=sum(s.output_tokens + s.reasoning_tokens for s in samples),
        historical_estimated_cost_usd=sum(latest_cost.values(), Decimal(0)),
    ), tuple(samples)


def projected_response_costs(
    rates: PricingRates, samples: tuple[TokenUsage, ...]
) -> tuple[Decimal, Decimal]:
    """额外 1024 输入 Token 是规划余量，不是新增模型实测。"""
    costs = sorted(
        estimate_result_cost(
            rates, sample.model_copy(update={"input_tokens": sample.input_tokens + 1024})
        )
        for sample in samples
    )
    return sum(costs, Decimal(0)) / len(costs), costs[math.ceil(len(costs) * 0.95) - 1]
