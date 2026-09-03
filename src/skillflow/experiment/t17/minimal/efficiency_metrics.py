"""离线效率和失败分类；Provider 未参与的测量必须明确 N/A。"""

from skillflow.experiment.t17.minimal.measurements import measured, not_applicable
from skillflow.experiment.t17.minimal.raw_loader import MinimalDomainData
from skillflow.experiment.t17.minimal.report_models import MinimalMeasurement


def efficiency_metrics(data: MinimalDomainData) -> dict[str, MinimalMeasurement]:
    """计时来自运行时 monotonic clock；虚拟时钟不冒充 API latency。"""
    records = data.records
    ids = tuple(item.run_id for item in records)
    steps = tuple(identifier for record in records for identifier in record.step_event_ids)
    result = {
        "agent_steps": measured(
            len(steps), 1, (*ids, *steps), unit="step_count", scope="core_total"
        ),
        "agent_steps_mean": measured(
            len(steps), len(records), (*ids, *steps), unit="steps_per_core"
        ),
        "actual_api_calls": measured(
            sum(item.actual_api_calls for item in records),
            1,
            ids,
            unit="call_count",
            scope="zero_api_domain_total",
        ),
        "estimated_cost_usd": measured(0, 1, ids, unit="USD", scope="zero_api_domain_total"),
        "reserved_budget_usd": measured(0, 1, ids, unit="USD", scope="zero_api_domain_total"),
        "harness_latency_ms_total": measured(
            sum(item.harness_wall_latency_ms for item in records),
            1,
            ids,
            unit="milliseconds",
            scope="core_harness_total",
        ),
        "harness_latency_ms_mean": measured(
            sum(item.harness_wall_latency_ms for item in records),
            len(records),
            ids,
            unit="milliseconds_per_core",
        ),
        "infrastructure_invalid": measured(0, len(records), ids),
        "budget_stopped": measured(0, len(records), ids),
    }
    for name in (
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "reasoning_tokens",
        "total_tokens",
        "provider_latency_ms",
    ):
        result[name] = not_applicable(
            "没有 Provider 请求或响应；Fake 文本长度不能当作 Token/Provider latency", unit=name
        )
    for name in ("refusal", "benign_refusal"):
        result[name] = not_applicable("固定 Scripted/Fake 协议不产生 Provider refusal 响应")
    for behavior in ("no_call", "schema_rejection"):
        result[behavior] = (
            measured(
                sum(
                    any(item.behavior == behavior for item in record.decision_journal)
                    for record in records
                ),
                len(records),
                (*ids, *steps),
            )
            if data.phase.domain == "fake_reference"
            else not_applicable("Scripted 没有模型响应")
        )
    result["fake_client_calls"] = (
        measured(
            sum(len(item.decision_journal) for item in records),
            1,
            (*ids, *steps),
            unit="fake_call_count",
            scope="core_total",
        )
        if data.phase.domain == "fake_reference"
        else not_applicable("Scripted 不调用 Fake Model Client")
    )
    for name, reason in (
        ("bootstrap_ci", "只预注册一个 semantic instance，不计算 cluster bootstrap"),
        ("cluster_consistency", "单 semantic instance、单 primary repeat，不估计跨簇稳定性"),
        ("scripted_determinism", "主 Matrix 不增加确定性重复；确定性由独立最小回归测试验证"),
        ("model_direction_agreement", "没有两个真实模型，不能声称跨模型方向一致"),
    ):
        result[name] = not_applicable(reason)
    return result
