"""T16 费用、步数、输出与重试的纯状态保护。"""

from dataclasses import dataclass, replace
from decimal import Decimal
from enum import StrEnum, unique
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from skillflow.models.base import StrictModel

PositiveInt = Annotated[int, Field(ge=1)]
NonNegativeInt = Annotated[int, Field(ge=0)]
PositiveMoney = Annotated[Decimal, Field(gt=0)]
NonNegativeMoney = Annotated[Decimal, Field(ge=0)]


class BudgetConfig(StrictModel):
    """可生成静态 Schema 的费用保护配置。"""

    schema_version: Literal["0.1"] = "0.1"
    allow_live: bool = False
    max_total_usd: PositiveMoney
    max_cost_per_run_usd: PositiveMoney
    max_agent_turns: PositiveInt
    max_output_tokens_per_turn: PositiveInt
    max_retries: NonNegativeInt

    @model_validator(mode="after")
    def require_nested_cost_limit(self) -> Self:
        """单 Run 上限不能大于总预算。"""
        if self.max_cost_per_run_usd > self.max_total_usd:
            raise PydanticCustomError("t16_run_budget_exceeds_total", "单 Run 预算不能大于总预算")
        return self


class CallReservation(StrictModel):
    """调用前保守预留的最大费用与输出。"""

    estimated_cost_usd: NonNegativeMoney
    max_output_tokens: PositiveInt


@unique
class BudgetLimit(StrEnum):
    """立即停止的封闭预算边界。"""

    LIVE_DISABLED = "live_disabled"
    TOTAL_COST = "total_cost"
    RUN_COST = "run_cost"
    AGENT_TURNS = "agent_turns"
    OUTPUT_TOKENS = "output_tokens"
    RETRIES = "retries"


@dataclass(frozen=True, slots=True)
class BudgetExceededError(RuntimeError):
    """一次调用在发生前被费用保护拒绝。"""

    limit: BudgetLimit
    attempted: str
    maximum: str

    def __str__(self) -> str:
        """返回稳定诊断。"""
        return f"{self.limit.value}: attempted={self.attempted}, maximum={self.maximum}"


@dataclass(frozen=True, slots=True)
class BudgetLedger:
    """不可变预算状态；每次许可返回一个新状态。"""

    config: BudgetConfig
    total_spent_usd: Decimal = Decimal(0)
    run_spent_usd: Decimal = Decimal(0)
    agent_turns: int = 0
    retries: int = 0

    def begin_run(self) -> "BudgetLedger":
        """保留总费用并重置单 Run 计数。"""
        return replace(self, run_spent_usd=Decimal(0), agent_turns=0, retries=0)

    def authorize_call(self, reservation: CallReservation) -> "BudgetLedger":
        """在调用前预留成本、一个 Agent turn 与输出上限。"""
        next_total = self.total_spent_usd + reservation.estimated_cost_usd
        next_run = self.run_spent_usd + reservation.estimated_cost_usd
        next_turn = self.agent_turns + 1
        if reservation.max_output_tokens > self.config.max_output_tokens_per_turn:
            self._exceeded(
                BudgetLimit.OUTPUT_TOKENS,
                reservation.max_output_tokens,
                self.config.max_output_tokens_per_turn,
            )
        if next_total > self.config.max_total_usd:
            self._exceeded(BudgetLimit.TOTAL_COST, next_total, self.config.max_total_usd)
        if next_run > self.config.max_cost_per_run_usd:
            self._exceeded(BudgetLimit.RUN_COST, next_run, self.config.max_cost_per_run_usd)
        if next_turn > self.config.max_agent_turns:
            self._exceeded(BudgetLimit.AGENT_TURNS, next_turn, self.config.max_agent_turns)
        return replace(
            self,
            total_spent_usd=next_total,
            run_spent_usd=next_run,
            agent_turns=next_turn,
        )

    def record_retry(self) -> "BudgetLedger":
        """在下一次尝试前消耗一次有限重试。"""
        next_retry = self.retries + 1
        if next_retry > self.config.max_retries:
            self._exceeded(BudgetLimit.RETRIES, next_retry, self.config.max_retries)
        return replace(self, retries=next_retry)

    @staticmethod
    def _exceeded(limit: BudgetLimit, attempted: object, maximum: object) -> None:
        raise BudgetExceededError(limit=limit, attempted=str(attempted), maximum=str(maximum))
