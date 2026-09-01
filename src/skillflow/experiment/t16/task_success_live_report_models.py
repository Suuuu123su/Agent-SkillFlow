"""T16-D.2 描述性 bridge 报告模型。"""

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field

from skillflow.experiment.t16.provider import TokenUsage
from skillflow.experiment.t16.task_success_statistics import (
    BootstrapEstimate,
    ConfidenceInterval,
)
from skillflow.models.base import NonEmptyStr, StrictModel

NonNegativeInt = Annotated[int, Field(ge=0)]
NonNegativeMoney = Annotated[Decimal, Field(ge=0)]


class T16D2ConditionReport(StrictModel):
    """单条件的三值 task success 与独立 Effect 计数。"""

    condition_id: NonEmptyStr
    scheduled: NonNegativeInt
    observed: NonNegativeInt
    task_success_true: NonNegativeInt
    task_success_false: NonNegativeInt
    task_success_na: NonNegativeInt
    target_effect_executed: NonNegativeInt
    refusal: NonNegativeInt
    no_call: NonNegativeInt
    schema_rejection: NonNegativeInt
    infrastructure_invalid: NonNegativeInt
    token_usage: TokenUsage
    latency_ms: NonNegativeInt
    estimated_cost_usd: NonNegativeMoney
    task_success_wilson_95: ConfidenceInterval | None
    target_effect_wilson_95: ConfidenceInterval | None


class T16D2JointOutcome(StrictModel):
    """task success 与目标 Effect 的二维结果。"""

    task_true_effect_true: NonNegativeInt
    task_true_effect_false: NonNegativeInt
    task_false_effect_true: NonNegativeInt
    task_false_effect_false: NonNegativeInt
    task_na_effect_true: NonNegativeInt
    task_na_effect_false: NonNegativeInt


class T16D2PairedEffectAnalysis(StrictModel):
    """两个条件或时序点的配对 Effect 差。"""

    target_successes: NonNegativeInt
    target_total: NonNegativeInt
    control_successes: NonNegativeInt
    control_total: NonNegativeInt
    estimate: BootstrapEstimate | None


class T16D2BridgeReport(StrictModel):
    """明确不与 v2 合并、也不是论文主实验的真实 bridge 报告。"""

    schema_version: Literal["0.1"] = "0.1"
    study_role: Literal["bridge_calibration"] = "bridge_calibration"
    simulation_only: Literal[False] = False
    formal_main_experiment: Literal[False] = False
    old_v2_mergeable: Literal[False] = False
    provider: Literal["openai"] = "openai"
    model_id: Literal["gpt-5.6-luna"] = "gpt-5.6-luna"
    provider_model_revisions: tuple[NonEmptyStr, ...]
    scheduled: Literal[48] = 48
    observed: NonNegativeInt
    condition_reports: tuple[T16D2ConditionReport, ...]
    joint_outcomes: T16D2JointOutcome
    c1_hiaa: BootstrapEstimate | None
    m2_session_1: T16D2PairedEffectAnalysis | None
    m2_session_3: T16D2PairedEffectAnalysis | None
    a1_claim_minus_neutralized: T16D2PairedEffectAnalysis | None
    formal_metrics: dict[NonEmptyStr, Literal["N/A"]]
    token_usage: TokenUsage
    api_call_count: NonNegativeInt
    total_estimated_cost_usd: NonNegativeMoney
    mean_cost_usd: NonNegativeMoney
    p50_cost_usd: NonNegativeMoney
    p95_cost_usd: NonNegativeMoney
    t16d_v2_evidence_acceptance: Literal["BLOCKED"] = "BLOCKED"
    t16d2_status: Literal["PASSED", "BLOCKED"]
    t16_e_recommendation: Literal["YES", "NO", "BLOCKED"]
