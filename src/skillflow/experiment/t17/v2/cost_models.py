"""一次总预算申请的冻结合同；不是新的价格核验或实际账单。"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from skillflow.experiment.t16.budget import BudgetConfig
from skillflow.experiment.t16.provider import PricingRates
from skillflow.experiment.t17.live_matrix import T17LiveStage
from skillflow.experiment.t17.minimal.contracts import Sha256
from skillflow.experiment.t17.v2.frozen import FrozenFile
from skillflow.models.base import NonEmptyStr, StrictModel

Money = Annotated[Decimal, Field(ge=0)]
Count = Annotated[int, Field(ge=0)]


class HistoricalUsage(StrictModel):
    """旧响应仅帮助费用规划，不进入新版评测总体。"""

    source_path: NonEmptyStr
    source_file: FrozenFile
    observed_responses: Count
    observed_input_tokens: Count
    observed_generated_tokens: Count
    historical_estimated_cost_usd: Money
    new_prompt_allowance_tokens: Literal[1024] = 1024
    interpretation: Literal["planning_only_not_new_experiment_evidence"] = (
        "planning_only_not_new_experiment_evidence"
    )


class StageCost(StrictModel):
    """执行图的调用上界、保守 Token 和明确阶段及单元预算。"""

    stage: T17LiveStage
    matrix_sha256: Sha256
    model_id: NonEmptyStr
    scheduled_core: Count
    scheduled_replay: Count
    no_failure_api_calls: Count
    max_network_attempts: Count
    worst_input_tokens: Count
    worst_output_including_reasoning_tokens: Count
    max_input_bytes_per_call: Literal[100000] = 100000
    expected_estimated_usd: Money
    historical_p95_projected_usd: Money
    uncapped_token_upper_cost_usd: Money
    budget: BudgetConfig
    rates: PricingRates
    rate_source: NonEmptyStr
    projection_kind: Literal["historical_per_response_with_prompt_allowance_not_guarantee"] = (
        "historical_per_response_with_prompt_allowance_not_guarantee"
    )
    count_scope: Literal["one_complete_attempt_including_bounded_request_retries"] = (
        "one_complete_attempt_including_bounded_request_retries"
    )
    whole_stage_restart: Literal["explicit_control_new_attempt_shared_original_dollar_caps"] = (
        "explicit_control_new_attempt_shared_original_dollar_caps"
    )


class CostPlan(StrictModel):
    """离线就绪后的唯一总额提案；未批准不能发起任何请求。"""

    schema_version: Literal["2.0"] = "2.0"
    protocol_id: NonEmptyStr
    protocol_relative_path: NonEmptyStr
    configuration_sha256: Sha256
    protocol_manifest: FrozenFile
    created_at: datetime
    price_basis_date: Literal["2026-09-03"] = "2026-09-03"
    price_policy: Literal["reuse_frozen_rates_no_lookup"] = "reuse_frozen_rates_no_lookup"
    historical: HistoricalUsage
    offline_evidence: dict[NonEmptyStr, FrozenFile]
    offline_relative_path: NonEmptyStr
    stages: tuple[StageCost, ...]
    requested_max_total_usd: Money
    used_in_new_protocol_usd: Literal["0"] = "0"
    remaining_requested_usd: Money
    api_calls_made: Literal[0] = 0
    authorization_status: Literal["pending_explicit_total_approval"] = (
        "pending_explicit_total_approval"
    )
    independent_review: Literal["REVIEW_UNAVAILABLE"] = "REVIEW_UNAVAILABLE"
    budget_can_stop_incomplete_stage: Literal[True] = True

    @model_validator(mode="after")
    def validate_caps(self) -> Self:
        """阶段顺序固定，总门不能低于各阶段上限之和。"""
        if tuple(s.stage for s in self.stages) != tuple(T17LiveStage):
            raise ValueError("v2_cost_plan_stage_order")
        total = sum((s.budget.max_total_usd for s in self.stages), Decimal(0))
        if total != self.requested_max_total_usd or self.remaining_requested_usd != total:
            raise ValueError("v2_cost_plan_total_cap")
        if any(s.budget.allow_live for s in self.stages):
            raise ValueError("v2_cost_plan_is_not_authorization")
        return self


class BudgetApproval(StrictModel):
    """金额、提案字节和用户明确批准相绑定，密钥不属于批准文件。"""

    schema_version: Literal["2.0"] = "2.0"
    approval_id: NonEmptyStr
    cost_plan_sha256: Sha256
    approved_at: datetime
    approved_max_total_usd: Money
    user_explicit_approval: Literal[True]
    approval_basis: NonEmptyStr
