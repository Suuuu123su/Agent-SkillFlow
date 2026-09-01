"""T16-C 真实模型执行的封闭配置与费用门。"""

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Final, Literal, NoReturn, Self

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from skillflow.experiment.t16.budget import BudgetConfig, BudgetLedger, CallReservation
from skillflow.experiment.t16.provider import (
    PricingStatus,
    ProviderConfig,
    ProviderKind,
    ReasoningEffort,
)
from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.validation import validate_yaml_document

PositiveMoney = Annotated[Decimal, Field(gt=0)]
SmokeAttempts = Annotated[int, Field(ge=1, le=3)]

LUNA_INPUT_USD = Decimal("0.20")
LUNA_CACHED_INPUT_USD = Decimal("0.02")
LUNA_CACHE_WRITE_USD = Decimal("0.25")
LUNA_OUTPUT_USD = Decimal("1.20")
USER_BUDGET_CEILING_USD = Decimal("20.00")
SMOKE_BUDGET_CEILING_USD = Decimal("0.50")
RUN_BUDGET_CEILING_USD = Decimal("0.05")
AGENT_TURN_CEILING = 16
OUTPUT_TOKEN_CEILING = 512
RETRY_CEILING = 1
LUNA_TEMPERATURE: None = None
LUNA_MODEL_ID = "gpt-5.6-luna"
GPT55_MODEL_ID = "gpt-5.5-2026-04-23"
GPT55_INPUT_USD = Decimal(5)
GPT55_CACHED_INPUT_USD = Decimal("0.5")
GPT55_OUTPUT_USD = Decimal(30)
GPT55_CACHE_WRITE_USD = Decimal(0)
T16E_CONFIG_ID: Final = "t16e-v3.1-canary-gpt-5.5-2026-04-23"


@dataclass(frozen=True, slots=True)
class _LiveModelProfile:
    """一个可执行模型的冻结身份、费率与费用上限。"""

    model_revision: str
    rates: tuple[Decimal, Decimal, Decimal, Decimal, Decimal]
    max_total_usd: Decimal
    max_run_usd: Decimal
    max_smoke_usd: Decimal
    prompt_cache_mode: str


_MODEL_PROFILES = {
    LUNA_MODEL_ID: _LiveModelProfile(
        LUNA_MODEL_ID,
        (
            LUNA_INPUT_USD,
            LUNA_CACHED_INPUT_USD,
            LUNA_OUTPUT_USD,
            LUNA_OUTPUT_USD,
            LUNA_CACHE_WRITE_USD,
        ),
        USER_BUDGET_CEILING_USD,
        RUN_BUDGET_CEILING_USD,
        SMOKE_BUDGET_CEILING_USD,
        "explicit",
    ),
    GPT55_MODEL_ID: _LiveModelProfile(
        GPT55_MODEL_ID,
        (
            GPT55_INPUT_USD,
            GPT55_CACHED_INPUT_USD,
            GPT55_OUTPUT_USD,
            GPT55_OUTPUT_USD,
            GPT55_CACHE_WRITE_USD,
        ),
        Decimal(1),
        Decimal("0.10"),
        Decimal(1),
        "automatic",
    ),
}


class T16CLiveConfig(StrictModel):
    """已注册 OpenAI 模型实验的不可扩张执行配置。"""

    schema_version: Literal["0.1", "0.2", "0.3"] = "0.1"
    id: NonEmptyStr = "t16c-gpt-5.6-luna"
    provider: ProviderConfig
    budget: BudgetConfig
    smoke_max_total_usd: PositiveMoney = Decimal("0.50")
    endpoint: Literal["https://api.openai.com/v1/responses"] = "https://api.openai.com/v1/responses"
    store_responses: Literal[False] = False
    prompt_cache_mode: Literal["explicit", "automatic"] = "explicit"
    transport_retries: Literal[0] = 0
    max_smoke_attempts: SmokeAttempts = 3

    @model_validator(mode="after")
    def require_frozen_execution(self) -> Self:
        """拒绝模型、价格、费用或数据保留边界漂移。"""
        profile = _MODEL_PROFILES.get(self.provider.model_id)
        if profile is None:
            self._invalid("模型不在已注册的 Live profile 中")
        self._require_provider(profile)
        self._require_budget(profile)
        return self

    def _require_provider(self, profile: _LiveModelProfile) -> None:
        if self.provider.kind is not ProviderKind.LIVE:
            self._invalid("T16-C 必须使用 Live Provider")
        if self.provider.model_revision != profile.model_revision:
            self._invalid("Provider model revision 与冻结 profile 不一致")
        if self.provider.reasoning_effort is not ReasoningEffort.MEDIUM:
            self._invalid("Live 实验必须保持预注册的 medium reasoning")
        if self.provider.temperature != LUNA_TEMPERATURE:
            self._invalid("medium reasoning 必须省略不兼容的 temperature")
        pricing = self.provider.pricing
        if pricing.status is not PricingStatus.LIVE_PINNED:
            self._invalid("Live 价格必须显式冻结")
        actual_rates = (
            pricing.input_per_million_usd,
            pricing.cached_input_per_million_usd,
            pricing.output_per_million_usd,
            pricing.reasoning_per_million_usd,
            pricing.cache_write_per_million_usd,
        )
        if actual_rates != profile.rates:
            self._invalid("模型价格与冻结 profile 不一致")
        if self.prompt_cache_mode != profile.prompt_cache_mode:
            self._invalid("Prompt cache mode 与冻结 profile 不一致")

    def _require_budget(self, profile: _LiveModelProfile) -> None:
        if not self.budget.allow_live:
            self._invalid("Live 实验必须显式开启 allow_live")
        if self.budget.max_total_usd > profile.max_total_usd:
            self._invalid("总预算超过模型 profile 上限")
        if self.smoke_max_total_usd > profile.max_smoke_usd:
            self._invalid("阶段预算超过模型 profile 上限")
        if self.smoke_max_total_usd > self.budget.max_total_usd:
            self._invalid("Smoke 预算不能超过总预算")
        if self.budget.max_cost_per_run_usd > profile.max_run_usd:
            self._invalid("单条实验链预算超过模型 profile 上限")
        if self.budget.max_agent_turns > AGENT_TURN_CEILING:
            self._invalid("每条实验链不能超过 16 个 Agent turn")
        if self.budget.max_output_tokens_per_turn > OUTPUT_TOKEN_CEILING:
            self._invalid("单轮输出不能超过 512 token")
        if self.budget.max_retries > 1:
            self._invalid("每条实验链最多允许一次重试")

    @staticmethod
    def _invalid(detail: str) -> NoReturn:
        raise PydanticCustomError("t16c_live_config_invalid", detail)

    def settle_call_budget(
        self,
        budget: BudgetLedger,
        reservation: CallReservation,
        actual_cost_usd: Decimal,
    ) -> BudgetLedger:
        """旧阶段保留已冻结的累计保守预留语义。"""
        del reservation, actual_cost_usd
        return budget

    @property
    def reuse_observed_input_tokens(self) -> bool:
        """Model1 保留冻结的逐次完整字节上界。"""
        return False


class T16ELiveConfig(T16CLiveConfig):
    """T16-E GPT-5.5 固定快照与实际费用结算合同。"""

    schema_version: Literal["0.3"] = "0.3"
    id: Literal["t16e-v3.1-canary-gpt-5.5-2026-04-23"] = "t16e-v3.1-canary-gpt-5.5-2026-04-23"
    budget_settlement_mode: Literal["actual_reconciled"] = "actual_reconciled"

    @model_validator(mode="after")
    def require_t16e_exact_bounds(self) -> Self:
        """T16-E 只接受用户本轮明确批准的模型与费用边界。"""
        if self.provider.model_id != GPT55_MODEL_ID:
            self._invalid("T16-E 模型必须是用户选择的 GPT-5.5 固定快照")
        if self.budget.max_total_usd != Decimal(1):
            self._invalid("T16-E 总预算必须精确为 1 美元")
        if self.budget.max_cost_per_run_usd != Decimal("0.10"):
            self._invalid("T16-E 单 Trial 预算必须精确为 0.10 美元")
        if self.budget.max_agent_turns != AGENT_TURN_CEILING:
            self._invalid("T16-E Agent Step 必须精确为 16")
        if self.budget.max_output_tokens_per_turn != OUTPUT_TOKEN_CEILING:
            self._invalid("T16-E 单轮输出必须精确为 512 Token")
        if self.budget.max_retries != RETRY_CEILING:
            self._invalid("T16-E 最大重试必须精确为 1")
        return self

    def settle_call_budget(
        self,
        budget: BudgetLedger,
        reservation: CallReservation,
        actual_cost_usd: Decimal,
    ) -> BudgetLedger:
        """成功响应后结算实际费用；无响应路径不会调用本方法。"""
        return budget.settle_call(reservation, actual_cost_usd)

    @property
    def reuse_observed_input_tokens(self) -> bool:
        """用前一响应的实际输入量约束增长历史的下一次预留。"""
        return True


def load_t16c_config(path: Path) -> T16CLiveConfig:
    """读取冻结的 T16-C Live 配置，且不访问环境变量。"""
    return validate_yaml_document(path, T16CLiveConfig)


def load_t16e_config(path: Path) -> T16ELiveConfig:
    """读取 T16-E 固定第二模型配置，且不访问环境变量。"""
    return validate_yaml_document(path, T16ELiveConfig)
