"""T16 的零网络 Provider 边界与费用估算模型。"""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum, unique
from typing import Annotated, Literal, Protocol, Self

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from skillflow.experiment.t16.budget import (
    BudgetExceededError,
    BudgetLedger,
    BudgetLimit,
    CallReservation,
)
from skillflow.models.base import NonEmptyStr, StrictModel

NonNegativeInt = Annotated[int, Field(ge=0)]
PositiveInt = Annotated[int, Field(ge=1)]
NonNegativeMoney = Annotated[Decimal, Field(ge=0)]
Temperature = Annotated[float, Field(ge=0, le=2)]


@unique
class ProviderKind(StrEnum):
    """T16 允许的 Provider 类型。"""

    FAKE = "fake"
    LIVE = "live"


@unique
class ReasoningEffort(StrEnum):
    """与具体厂商解耦的推理强度记录。"""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@unique
class PricingStatus(StrEnum):
    """价格是否已冻结到可执行状态。"""

    FAKE_ZERO = "fake_zero"
    LIVE_PENDING = "live_pending"
    LIVE_PINNED = "live_pinned"


@unique
class ProviderConfigurationReason(StrEnum):
    """Live/Fake Provider 的封闭配置错误。"""

    LIVE_PRICING_PENDING = "live_pricing_pending"
    INPUT_LIMIT_EXCEEDED = "input_limit_exceeded"
    OUTPUT_LIMIT_EXCEEDED = "output_limit_exceeded"


class PricingRates(StrictModel):
    """每百万 token 的美元估算价格。"""

    status: PricingStatus
    input_per_million_usd: NonNegativeMoney
    cached_input_per_million_usd: NonNegativeMoney
    output_per_million_usd: NonNegativeMoney
    reasoning_per_million_usd: NonNegativeMoney
    cache_write_per_million_usd: NonNegativeMoney = Decimal(0)


class ProviderConfig(StrictModel):
    """Fake/Live 共享的静态 Provider 配置。"""

    schema_version: Literal["0.1"] = "0.1"
    kind: ProviderKind
    model_id: NonEmptyStr
    model_revision: NonEmptyStr
    temperature: Temperature | None
    reasoning_effort: ReasoningEffort
    pricing: PricingRates

    @model_validator(mode="after")
    def require_safe_pricing_state(self) -> Self:
        """Fake 必须零价；Live 必须显式标记待定或已冻结。"""
        rates = (
            self.pricing.input_per_million_usd,
            self.pricing.cached_input_per_million_usd,
            self.pricing.output_per_million_usd,
            self.pricing.reasoning_per_million_usd,
            self.pricing.cache_write_per_million_usd,
        )
        if self.kind is ProviderKind.FAKE:
            if self.pricing.status is not PricingStatus.FAKE_ZERO or any(rates):
                raise PydanticCustomError("t16_fake_pricing_nonzero", "Fake Provider 必须为零价")
        elif self.pricing.status is PricingStatus.FAKE_ZERO:
            raise PydanticCustomError("t16_live_pricing_fake", "Live Provider 不能使用 Fake 价格")
        if self.pricing.status is PricingStatus.LIVE_PENDING and any(rates):
            raise PydanticCustomError("t16_pending_pricing_nonzero", "待定价格不能伪填数值")
        return self


class ProviderRequest(StrictModel):
    """一次模型调用前可审计的输入与硬输出上限。"""

    input_text: NonEmptyStr
    estimated_input_tokens: PositiveInt
    cached_input_tokens: NonNegativeInt = 0
    max_output_tokens: PositiveInt

    @model_validator(mode="after")
    def require_cached_subset(self) -> Self:
        """缓存输入 token 不能大于全部输入 token。"""
        if self.cached_input_tokens > self.estimated_input_tokens:
            raise PydanticCustomError("t16_cached_tokens_exceed_input", "缓存输入不能大于输入")
        return self


class TokenUsage(StrictModel):
    """TrialResult 所需的生成、缓存读写与推理 token 计数。"""

    input_tokens: NonNegativeInt
    cached_input_tokens: NonNegativeInt
    output_tokens: NonNegativeInt
    reasoning_tokens: NonNegativeInt
    cache_write_tokens: NonNegativeInt = 0

    @model_validator(mode="after")
    def require_cached_subset(self) -> Self:
        """缓存输入必须包含在输入总数内。"""
        if self.cached_input_tokens + self.cache_write_tokens > self.input_tokens:
            raise PydanticCustomError(
                "t16_cached_usage_exceeds_input",
                "缓存读取与写入用量之和不能大于输入",
            )
        return self


class ProviderCallResult(StrictModel):
    """模型唯一允许返回的内容；刻意不接受 origin_ids。"""

    output_text: str
    token_usage: TokenUsage
    latency_ms: NonNegativeInt


@dataclass(frozen=True, slots=True)
class ProviderInvocation:
    """一次已记账调用的结果。"""

    result: ProviderCallResult
    estimated_cost_usd: Decimal
    budget: BudgetLedger
    api_call_count: int = 1


@dataclass(frozen=True, slots=True)
class ProviderConfigurationError(RuntimeError):
    """Provider 配置尚不允许执行。"""

    reason: ProviderConfigurationReason

    def __str__(self) -> str:
        """返回稳定诊断。"""
        return self.reason.value


class LiveModelClient(Protocol):
    """T16-A 只能注入 Mock 的最小 Live Client 接口。"""

    def complete(
        self,
        config: ProviderConfig,
        request: ProviderRequest,
    ) -> ProviderCallResult:
        """返回一次模型结果。"""
        ...


class FakeProvider:
    """不进行 I/O 的固定响应 Provider。"""

    def __init__(self, config: ProviderConfig, response: ProviderCallResult) -> None:
        """保存严格配置与固定响应。"""
        self.config = config
        self._response = response

    def invoke(self, request: ProviderRequest, budget: BudgetLedger) -> ProviderInvocation:
        """执行一次零价本地响应。"""
        cost = estimate_result_cost(self.config.pricing, self._response.token_usage)
        updated = budget.authorize_call(
            CallReservation(
                estimated_cost_usd=estimate_reservation_cost(self.config, request),
                max_output_tokens=request.max_output_tokens,
            )
        )
        _require_usage_within_limits(self._response, request)
        return ProviderInvocation(
            result=self._response,
            estimated_cost_usd=cost,
            budget=updated,
        )


class LiveProvider:
    """只接受注入 Client 的 Live 边界；仓库不提供 HTTP 实现。"""

    def __init__(self, config: ProviderConfig, client: LiveModelClient) -> None:
        """保存严格配置与显式注入 Client。"""
        self.config = config
        self._client = client

    def invoke(self, request: ProviderRequest, budget: BudgetLedger) -> ProviderInvocation:
        """在许可、价格与预算检查后调用注入 Client。"""
        if not budget.config.allow_live:
            raise BudgetExceededError(
                limit=BudgetLimit.LIVE_DISABLED,
                attempted="live",
                maximum="disabled",
            )
        if self.config.pricing.status is not PricingStatus.LIVE_PINNED:
            raise ProviderConfigurationError(ProviderConfigurationReason.LIVE_PRICING_PENDING)
        updated = budget.authorize_call(
            CallReservation(
                estimated_cost_usd=estimate_reservation_cost(self.config, request),
                max_output_tokens=request.max_output_tokens,
            )
        )
        result = self._client.complete(self.config, request)
        _require_usage_within_limits(result, request)
        return ProviderInvocation(
            result=result,
            estimated_cost_usd=estimate_result_cost(self.config.pricing, result.token_usage),
            budget=updated,
        )


def estimate_result_cost(pricing: PricingRates, usage: TokenUsage) -> Decimal:
    """按实际 token 记录估算费用。"""
    uncached = usage.input_tokens - usage.cached_input_tokens - usage.cache_write_tokens
    million = Decimal(1_000_000)
    return (
        Decimal(uncached) * pricing.input_per_million_usd
        + Decimal(usage.cached_input_tokens) * pricing.cached_input_per_million_usd
        + Decimal(usage.cache_write_tokens) * pricing.cache_write_per_million_usd
        + Decimal(usage.output_tokens) * pricing.output_per_million_usd
        + Decimal(usage.reasoning_tokens) * pricing.reasoning_per_million_usd
    ) / million


def estimate_reservation_cost(config: ProviderConfig, request: ProviderRequest) -> Decimal:
    """在调用前按最坏输出组合预留费用。"""
    input_rate = max(
        config.pricing.input_per_million_usd,
        config.pricing.cached_input_per_million_usd,
        config.pricing.cache_write_per_million_usd,
    )
    output_rate = max(
        config.pricing.output_per_million_usd,
        config.pricing.reasoning_per_million_usd,
    )
    million = Decimal(1_000_000)
    return (
        Decimal(request.estimated_input_tokens) * input_rate
        + Decimal(request.max_output_tokens) * output_rate
    ) / million


def _require_usage_within_limits(
    result: ProviderCallResult,
    request: ProviderRequest,
) -> None:
    if result.token_usage.input_tokens > request.estimated_input_tokens:
        raise ProviderConfigurationError(ProviderConfigurationReason.INPUT_LIMIT_EXCEEDED)
    generated_tokens = result.token_usage.output_tokens + result.token_usage.reasoning_tokens
    if generated_tokens > request.max_output_tokens:
        raise ProviderConfigurationError(ProviderConfigurationReason.OUTPUT_LIMIT_EXCEEDED)
