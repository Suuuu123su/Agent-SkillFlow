"""T16-E 两个单 cluster 模型的描述性比较 Schema。"""

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field

from skillflow.experiment.t16.provider import TokenUsage
from skillflow.models.base import NonEmptyStr, StrictModel

NonNegativeInt = Annotated[int, Field(ge=0)]
NonNegativeMoney = Annotated[Decimal, Field(ge=0)]
Direction = Literal["negative", "zero", "positive"]
NotAvailable = Literal["not_available"]


class T16EConditionResult(StrictModel):
    """一个模型在一个 Canary 条件上的独立描述。"""

    condition_id: NonEmptyStr
    agent_steps: NonNegativeInt
    task_success: bool | None
    target_effect_requested: bool
    target_effect_executed: bool
    refusal: bool
    no_call: bool
    schema_rejection: bool
    token_usage: TokenUsage
    estimated_cost_usd: NonNegativeMoney
    latency_ms: NonNegativeInt


class T16EModelResult(StrictModel):
    """一个模型 11 条 Canary 的非合并统计。"""

    provider: Literal["openai"] = "openai"
    model_id: NonEmptyStr
    model_revisions: tuple[NonEmptyStr, ...]
    observed: Literal[11] = 11
    task_success_true: NonNegativeInt
    task_success_false: NonNegativeInt
    task_success_na: NonNegativeInt
    target_effect_requested: NonNegativeInt
    target_effect_executed: NonNegativeInt
    refusal: NonNegativeInt
    no_call: NonNegativeInt
    schema_rejection: NonNegativeInt
    api_calls: NonNegativeInt
    token_usage: TokenUsage
    estimated_cost_usd: NonNegativeMoney
    latency_ms: NonNegativeInt
    conditions: tuple[T16EConditionResult, ...]


class T16EC1Direction(StrictModel):
    """C1 四格的两个 skill 对比和描述性交互对比。"""

    model1_shared_off_delta: int
    model2_shared_off_delta: int
    shared_off_direction_model1: Direction
    shared_off_direction_model2: Direction
    model1_shared_on_delta: int
    model2_shared_on_delta: int
    shared_on_direction_model1: Direction
    shared_on_direction_model2: Direction
    model1_interaction_contrast: int
    model2_interaction_contrast: int
    consistent: bool


class T16EPairedDirection(StrictModel):
    """一个 target/control 配对的二值差与方向一致性。"""

    model1_delta: int
    model2_delta: int
    model1_direction: Direction
    model2_direction: Direction
    consistent: bool


class T16EFormalMetrics(StrictModel):
    """本阶段明确不可计算的正式研究指标。"""

    uea: NotAvailable = "not_available"
    alr: NotAvailable = "not_available"
    rir_1: NotAvailable = "not_available"
    rir_3: NotAvailable = "not_available"
    provenance: NotAvailable = "not_available"


class T16ECrossModelComparison(StrictModel):
    """不合并模型、不做显著性推断的 T16-E 阶段证据。"""

    schema_version: Literal["0.1"] = "0.1"
    analysis_scope: Literal["descriptive_two_model_single_cluster"] = (
        "descriptive_two_model_single_cluster"
    )
    models_pooled: Literal[False] = False
    single_cluster_per_model: Literal[True] = True
    statistical_significance: None = None
    bootstrap_ci: None = None
    model1: T16EModelResult
    model2: T16EModelResult
    task_success_rate_delta: Decimal
    c1_direction: T16EC1Direction
    m2_direction: T16EPairedDirection
    a1_direction: T16EPairedDirection
    potential_model_difference_conditions: tuple[NonEmptyStr, ...]
    formal_metrics: T16EFormalMetrics = T16EFormalMetrics()
    sample_expansion_recommended: Literal[True] = True
