"""第二模型替换的有限授权；旧费用保留，旧模型记录不进入新分母。"""

from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from skillflow.experiment.t17.live_matrix import T17LiveStage
from skillflow.experiment.t17.v2.cost_models import StageCost
from skillflow.models.base import StrictModel


class ReplacementPlan(StrictModel):
    """用户批准的模型、阶段额度和前置结果。"""

    approved_prefix: str | None = None
    approved_formal_prefix: str | None = None
    recorded_core_raw: str | None = None
    recorded_core_ordinal: int | None = None
    usage_reference: str | None = None
    prerequisite_outcomes: tuple[str, ...] = ()
    parallel_with_second_model: bool = False
    parallel_unspent_stage_cap_usd: Decimal = Decimal(0)
    protocol: str
    output: str
    source_snapshot: str
    original_approved_usd: Decimal = Decimal("58.25")
    historical_estimated_usd: Decimal
    historical_reserved_usd: Decimal
    remaining_approved_usd: Decimal
    allocated_usd: Decimal
    stages: tuple[StageCost, ...]
    model: Literal["deepseek-v4-flash", "gpt-5.6-luna"] = "deepseek-v4-flash"
    endpoint: Literal[
        "https://api.deepseek.com/responses", "https://api.openai.com/v1/responses"
    ] = "https://api.deepseek.com/responses"
    requested_reasoning: Literal["medium"] = "medium"
    provider_effective_reasoning: Literal["high", "medium"] = "high"
    instruction_role: Literal["system", "developer"] = "system"
    model_version_limit: str = "服务返回的模型标识必须固定；别名不等于可验证的不可变快照。"
    price_policy: str = "使用切换时已有费率作估算，不重新查询价格，不代表供应商账单。"
    comparison_limit: str = "控制指令正文相同；角色和推理档位按接口映射，须在跨模型解释中注明。"
    scope: str = "仅替换 G：24/18 预检通过后 360/270；E/F 不重跑，H 仍用 Luna。"

    @model_validator(mode="after")
    def validate_provider_scope(self) -> Self:
        """同一安全执行入口仅允许既定 G 或单独 H，禁止跨提供方用钥。"""
        if self.model == "gpt-5.6-luna":
            expected = (T17LiveStage.DEFENSE,)
            correct = (
                self.endpoint == "https://api.openai.com/v1/responses"
                and self.instruction_role == "developer"
                and self.provider_effective_reasoning == "medium"
                and len(self.prerequisite_outcomes) == (1 if self.parallel_with_second_model else 2)
            )
        else:
            expected = (T17LiveStage.MODEL2_CANARY, T17LiveStage.MODEL2)
            correct = (
                self.endpoint == "https://api.deepseek.com/responses"
                and self.instruction_role == "system"
                and self.provider_effective_reasoning == "high"
            )
        if not correct or tuple(s.stage for s in self.stages) != expected:
            raise ValueError("replacement_provider_stage_scope_mismatch")
        if self.allocated_usd + self.parallel_unspent_stage_cap_usd > self.remaining_approved_usd:
            raise ValueError("replacement_parallel_total_cap_mismatch")
        return self


class ReplacementJob(StrictModel):
    """不含密钥的单次工作进程输入。"""

    root: str
    plan: str
    approval: str
    stage_index: Annotated[int, Field(ge=0, le=1)]
    attempt_number: Annotated[int, Field(ge=1)]
    remaining_usd: Annotated[Decimal, Field(gt=0)]
    first_ordinal: Annotated[int, Field(ge=1)] = 1
    previous_selection: str | None = None
    recorded_core_raw: str | None = None
    source_raw: str | None = None
    snapshot_relative_path: str
