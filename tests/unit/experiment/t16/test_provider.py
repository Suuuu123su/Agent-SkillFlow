from decimal import Decimal

import pytest
from pydantic import ValidationError

from skillflow.experiment.t16.budget import BudgetConfig, BudgetExceededError, BudgetLedger
from skillflow.experiment.t16.provider import (
    FakeProvider,
    LiveProvider,
    PricingRates,
    PricingStatus,
    ProviderCallResult,
    ProviderConfig,
    ProviderConfigurationError,
    ProviderConfigurationReason,
    ProviderKind,
    ProviderRequest,
    ReasoningEffort,
    TokenUsage,
    estimate_result_cost,
)


def fake_config() -> ProviderConfig:
    return ProviderConfig(
        kind=ProviderKind.FAKE,
        model_id="fake-t16",
        model_revision="deterministic-v1",
        temperature=0,
        reasoning_effort=ReasoningEffort.NONE,
        pricing=PricingRates(
            status=PricingStatus.FAKE_ZERO,
            input_per_million_usd=Decimal(0),
            cached_input_per_million_usd=Decimal(0),
            output_per_million_usd=Decimal(0),
            reasoning_per_million_usd=Decimal(0),
        ),
    )


def live_config() -> ProviderConfig:
    return ProviderConfig(
        kind=ProviderKind.LIVE,
        model_id="mock-live-model",
        model_revision="mock-revision",
        temperature=0.2,
        reasoning_effort=ReasoningEffort.MEDIUM,
        pricing=PricingRates(
            status=PricingStatus.LIVE_PINNED,
            input_per_million_usd=Decimal(1),
            cached_input_per_million_usd=Decimal("0.5"),
            cache_write_per_million_usd=Decimal("1.25"),
            output_per_million_usd=Decimal(4),
            reasoning_per_million_usd=Decimal(2),
        ),
    )


def response() -> ProviderCallResult:
    return ProviderCallResult(
        output_text="fixed",
        token_usage=TokenUsage(
            input_tokens=100,
            cached_input_tokens=20,
            output_tokens=10,
            reasoning_tokens=5,
        ),
        latency_ms=3,
    )


def request() -> ProviderRequest:
    return ProviderRequest(
        input_text="fixed input",
        estimated_input_tokens=100,
        cached_input_tokens=20,
        max_output_tokens=50,
    )


def ledger(*, allow_live: bool = False) -> BudgetLedger:
    return BudgetLedger(
        BudgetConfig(
            allow_live=allow_live,
            max_total_usd=Decimal(10),
            max_cost_per_run_usd=Decimal(1),
            max_agent_turns=3,
            max_output_tokens_per_turn=100,
            max_retries=1,
        )
    )


class MockLiveClient:
    def __init__(self) -> None:
        self.calls = 0

    def complete(
        self,
        config: ProviderConfig,
        request: ProviderRequest,
    ) -> ProviderCallResult:
        self.calls += 1
        return response()


def test_fake_provider_is_zero_cost_and_deterministic() -> None:
    # Given: 固定响应且零价的 Fake Provider。
    provider = FakeProvider(fake_config(), response())

    # When: 执行一次本地调用。
    invocation = provider.invoke(request(), ledger())

    # Then: 只记一次调用且费用为零。
    assert invocation.result == response()
    assert invocation.api_call_count == 1
    assert invocation.estimated_cost_usd == Decimal(0)
    assert invocation.budget.agent_turns == 1


def test_live_provider_is_blocked_before_mock_client_by_default() -> None:
    # Given: 注入的 Mock Client 与默认关闭 live 的预算。
    client = MockLiveClient()
    provider = LiveProvider(live_config(), client)

    # When / Then: 调用在进入 Client 前被拒绝。
    with pytest.raises(BudgetExceededError):
        provider.invoke(request(), ledger())
    assert client.calls == 0


def test_live_interface_uses_only_injected_mock_client_when_enabled() -> None:
    # Given: 测试专用许可与注入 Mock Client。
    client = MockLiveClient()
    provider = LiveProvider(live_config(), client)

    # When: 在单元测试中打开接口。
    invocation = provider.invoke(request(), ledger(allow_live=True))

    # Then: 仅调用注入对象，产生可审计费用。
    assert client.calls == 1
    assert invocation.estimated_cost_usd == Decimal("0.00014")
    assert invocation.budget.agent_turns == 1


def test_model_output_cannot_submit_origin_ids() -> None:
    # Given: 伪装成模型来源声明的额外字段。
    payload = response().model_dump(mode="python")
    payload["origin_ids"] = ["model:claimed"]

    # When / Then: Provider 输出边界拒绝未知 provenance。
    with pytest.raises(ValidationError):
        ProviderCallResult.model_validate(payload)


def test_cost_estimate_separates_all_token_classes() -> None:
    # Given: 输入、缓存、输出和推理 token 的不同价格。
    pricing = live_config().pricing

    # When: 计算固定使用量。
    cost = estimate_result_cost(pricing, response().token_usage)

    # Then: 未缓存输入不会被重复计价。
    assert cost == Decimal("0.00014")


def test_cache_write_tokens_are_recorded_and_billed_without_double_counting() -> None:
    usage = response().token_usage.model_copy(update={"cache_write_tokens": 4})

    cost = estimate_result_cost(live_config().pricing, usage)

    assert cost == Decimal("0.000141")


def test_cache_read_and_write_breakdowns_must_fit_inside_input_total() -> None:
    with pytest.raises(ValidationError):
        TokenUsage(
            input_tokens=100,
            cached_input_tokens=60,
            cache_write_tokens=41,
            output_tokens=0,
            reasoning_tokens=0,
        )


@pytest.mark.parametrize(
    ("usage", "reason"),
    [
        (
            TokenUsage(
                input_tokens=101,
                cached_input_tokens=20,
                output_tokens=10,
                reasoning_tokens=5,
            ),
            ProviderConfigurationReason.INPUT_LIMIT_EXCEEDED,
        ),
        (
            TokenUsage(
                input_tokens=100,
                cached_input_tokens=20,
                output_tokens=40,
                reasoning_tokens=11,
            ),
            ProviderConfigurationReason.OUTPUT_LIMIT_EXCEEDED,
        ),
    ],
)
def test_provider_rejects_usage_beyond_reserved_limits(
    usage: TokenUsage,
    reason: ProviderConfigurationReason,
) -> None:
    # Given: Provider 自报的使用量超过调用前费用预留边界。
    oversized = response().model_copy(update={"token_usage": usage})
    provider = FakeProvider(fake_config(), oversized)

    # When / Then: 不能把超额 token 静默记入一次已保护调用。
    with pytest.raises(ProviderConfigurationError) as error:
        provider.invoke(request(), ledger())
    assert error.value.reason is reason
