"""从两个独立 Canary Attempt 构造 T16-E 描述性比较。"""

from dataclasses import dataclass
from decimal import Decimal

from skillflow.experiment.t16.live_record_builders import add_usage, zero_usage
from skillflow.experiment.t16.t16e_models import (
    Direction,
    T16EC1Direction,
    T16EConditionResult,
    T16ECrossModelComparison,
    T16EModelResult,
    T16EPairedDirection,
)
from skillflow.experiment.t16.task_success_canary_engine_support import CANARY_COUNT
from skillflow.experiment.t16.task_success_canary_models import T16D2CanaryRunSummary
from skillflow.experiment.t16.task_success_live_models import T16D2RawTrialRecord

INCOMPLETE_CANARY = "跨模型比较只接受完整 PASSED 的 11 条 Canary"
CONDITIONS_NOT_UNIQUE = "跨模型比较条件不唯一"
SUMMARY_RAW_MISMATCH = "摘要与 Raw condition 不一致"
MULTIPLE_MODEL_IDS = "单个 Attempt 出现多个 Model ID"


@dataclass(frozen=True, slots=True)
class T16EComparisonInputs:
    """两个独立 Attempt 的严格摘要与原始记录。"""

    model1_summary: T16D2CanaryRunSummary
    model1_records: tuple[T16D2RawTrialRecord, ...]
    model2_summary: T16D2CanaryRunSummary
    model2_records: tuple[T16D2RawTrialRecord, ...]


@dataclass(frozen=True, slots=True)
class T16EComparisonError(RuntimeError):
    """比较输入不满足两个完整 11 条 Canary。"""

    detail: str

    def __str__(self) -> str:
        """返回不含模型正文的稳定诊断。"""
        return self.detail


def build_t16e_comparison(inputs: T16EComparisonInputs) -> T16ECrossModelComparison:
    """分别描述两个模型，只比较预注册配对的方向。"""
    model1 = _describe_model(inputs.model1_summary, inputs.model1_records)
    model2 = _describe_model(inputs.model2_summary, inputs.model2_records)
    first = {item.condition_id: item for item in model1.conditions}
    second = {item.condition_id: item for item in model2.conditions}
    c1 = _c1_direction(first, second)
    m2 = _paired_direction(first, second, "m2-target", "m2-control")
    a1 = _paired_direction(first, second, "a1-claim", "a1-neutralized")
    differences = tuple(
        condition_id
        for condition_id in first
        if _result_signature(first[condition_id]) != _result_signature(second[condition_id])
    )
    return T16ECrossModelComparison(
        model1=model1,
        model2=model2,
        task_success_rate_delta=(
            Decimal(model2.task_success_true) / Decimal(CANARY_COUNT)
            - Decimal(model1.task_success_true) / Decimal(CANARY_COUNT)
        ),
        c1_direction=c1,
        m2_direction=m2,
        a1_direction=a1,
        potential_model_difference_conditions=differences,
    )


def _describe_model(
    summary: T16D2CanaryRunSummary,
    records: tuple[T16D2RawTrialRecord, ...],
) -> T16EModelResult:
    if (
        summary.status != "PASSED"
        or summary.observed != CANARY_COUNT
        or len(records) != CANARY_COUNT
    ):
        raise T16EComparisonError(INCOMPLETE_CANARY)
    by_condition = {item.live_trial.result.condition_id: item for item in records}
    if len(by_condition) != CANARY_COUNT:
        raise T16EComparisonError(CONDITIONS_NOT_UNIQUE)
    usage = zero_usage()
    conditions: list[T16EConditionResult] = []
    for trial in summary.trials:
        record = by_condition.get(trial.condition_id)
        if record is None:
            raise T16EComparisonError(SUMMARY_RAW_MISMATCH)
        result = record.live_trial.result
        usage = add_usage(usage, result.token_usage)
        conditions.append(
            T16EConditionResult(
                condition_id=trial.condition_id,
                agent_steps=trial.agent_steps,
                task_success=result.task_success,
                target_effect_requested=result.target_effect_requested,
                target_effect_executed=result.target_effect_executed,
                refusal=result.refusal,
                no_call=result.no_call,
                schema_rejection=result.schema_rejection,
                token_usage=result.token_usage,
                estimated_cost_usd=result.estimated_cost_usd,
                latency_ms=result.latency_ms,
            )
        )
    model_ids = {item.live_trial.result.model_id for item in records}
    if len(model_ids) != 1:
        raise T16EComparisonError(MULTIPLE_MODEL_IDS)
    return T16EModelResult(
        model_id=next(iter(model_ids)),
        model_revisions=summary.provider_model_revisions,
        task_success_true=summary.task_success_true,
        task_success_false=summary.task_success_false,
        task_success_na=summary.task_success_na,
        target_effect_requested=summary.target_effect_requested_count,
        target_effect_executed=summary.target_effect_executed_count,
        refusal=sum(item.refusal for item in conditions),
        no_call=sum(item.no_call for item in conditions),
        schema_rejection=sum(item.schema_rejection for item in conditions),
        api_calls=summary.api_call_count,
        token_usage=usage,
        estimated_cost_usd=sum(
            (item.estimated_cost_usd for item in conditions),
            start=Decimal(0),
        ),
        latency_ms=sum(item.latency_ms for item in conditions),
        conditions=tuple(conditions),
    )


def _c1_direction(
    model1: dict[str, T16EConditionResult],
    model2: dict[str, T16EConditionResult],
) -> T16EC1Direction:
    first_off = _effect(model1, "c1-p10") - _effect(model1, "c1-p00")
    second_off = _effect(model2, "c1-p10") - _effect(model2, "c1-p00")
    first_on = _effect(model1, "c1-p11") - _effect(model1, "c1-p01")
    second_on = _effect(model2, "c1-p11") - _effect(model2, "c1-p01")
    return T16EC1Direction(
        model1_shared_off_delta=first_off,
        model2_shared_off_delta=second_off,
        shared_off_direction_model1=_direction(first_off),
        shared_off_direction_model2=_direction(second_off),
        model1_shared_on_delta=first_on,
        model2_shared_on_delta=second_on,
        shared_on_direction_model1=_direction(first_on),
        shared_on_direction_model2=_direction(second_on),
        model1_interaction_contrast=first_on - first_off,
        model2_interaction_contrast=second_on - second_off,
        consistent=_direction(first_off) == _direction(second_off)
        and _direction(first_on) == _direction(second_on),
    )


def _paired_direction(
    model1: dict[str, T16EConditionResult],
    model2: dict[str, T16EConditionResult],
    target: str,
    control: str,
) -> T16EPairedDirection:
    first = _effect(model1, target) - _effect(model1, control)
    second = _effect(model2, target) - _effect(model2, control)
    return T16EPairedDirection(
        model1_delta=first,
        model2_delta=second,
        model1_direction=_direction(first),
        model2_direction=_direction(second),
        consistent=_direction(first) == _direction(second),
    )


def _effect(results: dict[str, T16EConditionResult], condition_id: str) -> int:
    result = results.get(condition_id)
    if result is None:
        detail = f"缺少方向条件: {condition_id}"
        raise T16EComparisonError(detail)
    return int(result.target_effect_executed)


def _direction(delta: int) -> Direction:
    if delta > 0:
        return "positive"
    if delta < 0:
        return "negative"
    return "zero"


def _result_signature(result: T16EConditionResult) -> tuple[bool | None, ...]:
    return (
        result.task_success,
        result.target_effect_requested,
        result.target_effect_executed,
        result.refusal,
        result.no_call,
        result.schema_rejection,
    )
