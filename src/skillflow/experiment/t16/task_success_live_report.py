"""T16-D.2 条件、二维结果与探索性配对统计。"""

import math
from decimal import Decimal

from skillflow.experiment.t16.live_record_builders import add_usage, zero_usage
from skillflow.experiment.t16.task_success_live_models import (
    T16D2RawTrialRecord,
    T16D2RunSummary,
)
from skillflow.experiment.t16.task_success_live_report_models import (
    T16D2BridgeReport,
    T16D2ConditionReport,
    T16D2JointOutcome,
)
from skillflow.experiment.t16.task_success_live_report_statistics import (
    c1_hiaa,
    m2_session,
    paired_conditions,
)
from skillflow.experiment.t16.task_success_statistics import (
    wilson_interval,
)

CONDITION_ORDER = (
    "b0",
    "g0",
    "n0",
    "c1-p00",
    "c1-p01",
    "c1-p10",
    "c1-p11",
    "m2-control",
    "m2-target",
    "a1-claim",
    "a1-neutralized",
    "a2-structured-confirmation",
)


def build_t16d2_bridge_report(
    records: tuple[T16D2RawTrialRecord, ...],
    summary: T16D2RunSummary,
) -> T16D2BridgeReport:
    """只从不可变原始记录计算 bridge 描述统计。"""
    condition_reports = tuple(
        _condition_report(condition_id, records) for condition_id in CONDITION_ORDER
    )
    costs = tuple(sorted(item.live_trial.result.estimated_cost_usd for item in records))
    revisions = tuple(
        sorted({revision for item in records for revision in item.provider_model_revisions})
    )
    return T16D2BridgeReport(
        provider_model_revisions=revisions,
        observed=len(records),
        condition_reports=condition_reports,
        joint_outcomes=_joint_outcomes(records),
        c1_hiaa=c1_hiaa(records),
        m2_session_1=m2_session(records, 1),
        m2_session_3=m2_session(records, 3),
        a1_claim_minus_neutralized=paired_conditions(
            records,
            "a1-claim",
            "a1-neutralized",
        ),
        formal_metrics={
            "UEA": "N/A",
            "ALR": "N/A",
            "RIR(1)": "N/A",
            "RIR(3)": "N/A",
            "provenance": "N/A",
        },
        token_usage=summary.token_usage,
        api_call_count=summary.api_call_count,
        total_estimated_cost_usd=summary.actual_estimated_cost_usd,
        mean_cost_usd=(summary.actual_estimated_cost_usd / len(records) if records else Decimal(0)),
        p50_cost_usd=_percentile_cost(costs, 0.50),
        p95_cost_usd=_percentile_cost(costs, 0.95),
        t16d2_status="PASSED" if summary.final_gate_passed else "BLOCKED",
        t16_e_recommendation="YES" if summary.final_gate_passed else "BLOCKED",
    )


def _condition_report(
    condition_id: str,
    records: tuple[T16D2RawTrialRecord, ...],
) -> T16D2ConditionReport:
    selected = tuple(
        item for item in records if item.live_trial.result.condition_id == condition_id
    )
    valid_task = tuple(item for item in selected if item.live_trial.result.task_success is not None)
    usage = zero_usage()
    for item in selected:
        usage = add_usage(usage, item.live_trial.result.token_usage)
    task_true = sum(item.live_trial.result.task_success is True for item in selected)
    effect = sum(item.live_trial.result.target_effect_executed for item in selected)
    return T16D2ConditionReport(
        condition_id=condition_id,
        scheduled=4,
        observed=len(selected),
        task_success_true=task_true,
        task_success_false=sum(item.live_trial.result.task_success is False for item in selected),
        task_success_na=sum(item.live_trial.result.task_success is None for item in selected),
        target_effect_executed=effect,
        refusal=sum(item.live_trial.result.refusal for item in selected),
        no_call=sum(item.live_trial.result.no_call for item in selected),
        schema_rejection=sum(item.live_trial.result.schema_rejection for item in selected),
        infrastructure_invalid=sum(_infrastructure_invalid(item) for item in selected),
        token_usage=usage,
        latency_ms=sum(item.live_trial.result.latency_ms for item in selected),
        estimated_cost_usd=sum(
            (item.live_trial.result.estimated_cost_usd for item in selected),
            start=Decimal(0),
        ),
        task_success_wilson_95=(
            wilson_interval(task_true, len(valid_task)) if valid_task else None
        ),
        target_effect_wilson_95=(wilson_interval(effect, len(selected)) if selected else None),
    )


def _joint_outcomes(
    records: tuple[T16D2RawTrialRecord, ...],
) -> T16D2JointOutcome:
    def count(task: bool | None, effect: bool) -> int:
        return sum(
            item.live_trial.result.task_success is task
            and item.live_trial.result.target_effect_executed is effect
            for item in records
        )

    return T16D2JointOutcome(
        task_true_effect_true=count(True, True),
        task_true_effect_false=count(True, False),
        task_false_effect_true=count(False, True),
        task_false_effect_false=count(False, False),
        task_na_effect_true=count(None, True),
        task_na_effect_false=count(None, False),
    )


def _percentile_cost(costs: tuple[Decimal, ...], probability: float) -> Decimal:
    if not costs:
        return Decimal(0)
    return costs[max(0, math.ceil(len(costs) * probability) - 1)]


def _infrastructure_invalid(record: T16D2RawTrialRecord) -> bool:
    result = record.live_trial.result
    return result.timeout or result.rate_limit or result.provider_error
