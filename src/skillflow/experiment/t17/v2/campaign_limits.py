"""跨进程和跨尝试的纯预算计算，不会因重开实验而增加额度。"""

from dataclasses import dataclass
from decimal import Decimal

from skillflow.experiment.t16.budget import BudgetConfig
from skillflow.experiment.t17.live_matrix import T17LiveStage
from skillflow.experiment.t17.v2.campaign_models import StageOutcome


@dataclass(frozen=True, slots=True)
class SpendingHistory:
    """成功阶段和失败尝试分别保存，计费时两者都不能省略。"""

    passed: tuple[StageOutcome, ...] = ()
    failed: tuple[StageOutcome, ...] = ()

    def __post_init__(self) -> None:
        """同一原始目录不能被两次扣款或同时冒充成功与失败。"""
        paths = tuple(s.raw_relative_path for s in self.all_outcomes)
        if len(paths) != len(set(paths)):
            raise ValueError("v2_duplicate_attempt_accounting")

    @property
    def all_outcomes(self) -> tuple[StageOutcome, ...]:
        """包括无完整响应的失败尝试。"""
        return (*self.passed, *self.failed)

    @property
    def estimated_usd(self) -> Decimal:
        """已返回用量对应的费用估算；未知响应不当成实际零消费。"""
        return sum((s.usage.estimated_cost_usd for s in self.all_outcomes), Decimal(0))

    @property
    def reserved_usd(self) -> Decimal:
        """真实估算加未决请求的保守占用。"""
        return sum((s.usage.reserved_cost_usd for s in self.all_outcomes), Decimal(0))


def remaining_budget(
    stage: T17LiveStage, original: BudgetConfig, approved: Decimal, history: SpendingHistory
) -> BudgetConfig:
    """总门、阶段门、单任务门同时收紧，绝不因失败自动加钱。"""
    stage_used = sum(
        (s.usage.reserved_cost_usd for s in history.all_outcomes if s.stage == stage), Decimal(0)
    )
    remaining = min(original.max_total_usd - stage_used, approved - history.reserved_usd)
    if remaining <= 0:
        raise ValueError("v2_budget_exhausted")
    return BudgetConfig.model_validate(
        {
            **original.model_dump(),
            "max_total_usd": remaining,
            "max_cost_per_run_usd": min(original.max_cost_per_run_usd, remaining),
        }
    )
