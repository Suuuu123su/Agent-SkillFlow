import ast
import socket
from decimal import Decimal
from pathlib import Path

import pytest

from skillflow.experiment.t16.budget import BudgetConfig, BudgetLedger
from skillflow.experiment.t16.provider import (
    FakeProvider,
    LiveProvider,
    PricingRates,
    PricingStatus,
    ProviderCallResult,
    ProviderConfig,
    ProviderKind,
    ProviderRequest,
    ReasoningEffort,
    TokenUsage,
)
from skillflow.experiment.t16.trial import (
    ProvenanceRecord,
    ProvenanceStatus,
    TrialOutcome,
    TrialResult,
)


def response() -> ProviderCallResult:
    return ProviderCallResult(
        output_text="fixed-safe-result",
        token_usage=TokenUsage(
            input_tokens=8,
            cached_input_tokens=0,
            output_tokens=4,
            reasoning_tokens=0,
        ),
        latency_ms=1,
    )


def request() -> ProviderRequest:
    return ProviderRequest(
        input_text="fixed input",
        estimated_input_tokens=8,
        max_output_tokens=16,
    )


def budget(*, allow_live: bool) -> BudgetLedger:
    return BudgetLedger(
        BudgetConfig(
            allow_live=allow_live,
            max_total_usd=Decimal(1),
            max_cost_per_run_usd=Decimal("0.1"),
            max_agent_turns=2,
            max_output_tokens_per_turn=16,
            max_retries=0,
        )
    )


def config(kind: ProviderKind) -> ProviderConfig:
    status = PricingStatus.FAKE_ZERO if kind is ProviderKind.FAKE else PricingStatus.LIVE_PINNED
    return ProviderConfig(
        kind=kind,
        model_id=f"{kind.value}-test-model",
        model_revision="test-only-v1",
        temperature=0,
        reasoning_effort=ReasoningEffort.NONE,
        pricing=PricingRates(
            status=status,
            input_per_million_usd=Decimal(0),
            cached_input_per_million_usd=Decimal(0),
            output_per_million_usd=Decimal(0),
            reasoning_per_million_usd=Decimal(0),
        ),
    )


class MockLiveClient:
    def complete(
        self,
        config: ProviderConfig,
        request: ProviderRequest,
    ) -> ProviderCallResult:
        return response()


def forbid_network(*args: object, **kwargs: object) -> None:
    message = "T16-A 测试检测到意外网络调用"
    raise AssertionError(message)


def test_fake_and_mock_live_complete_with_network_hard_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: 最底层建连函数被替换成立即失败。
    monkeypatch.setattr(socket, "create_connection", forbid_network)
    monkeypatch.setattr(socket, "socket", forbid_network)
    fake = FakeProvider(config(ProviderKind.FAKE), response())
    mock_live = LiveProvider(config(ProviderKind.LIVE), MockLiveClient())

    # When: Fake 与仅注入 Mock Client 的 Live 接口各执行一次。
    fake_result = fake.invoke(request(), budget(allow_live=False))
    live_result = mock_live.invoke(request(), budget(allow_live=True))

    # Then: 两条链均完成且未触发任何网络建连。
    assert fake_result.result.output_text == "fixed-safe-result"
    assert live_result.result.output_text == "fixed-safe-result"


def test_provider_module_has_no_network_or_environment_imports() -> None:
    # Given: T16-A Provider 模块的语法树。
    source = Path("src/skillflow/experiment/t16/provider.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    # When: 提取直接 import 的根模块。
    imported = {
        alias.name.split(".", maxsplit=1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported.update(
        node.module.split(".", maxsplit=1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    )

    # Then: 实现层没有网络库或环境读取入口。
    assert imported.isdisjoint({"aiohttp", "http", "os", "requests", "socket", "urllib"})


def test_fake_invocation_can_be_recorded_as_structured_na() -> None:
    # Given: 一个 Fake 结果和缺失平台 Hook 的来源状态。
    invocation = FakeProvider(config(ProviderKind.FAKE), response()).invoke(
        request(),
        budget(allow_live=False),
    )

    # When: 写入统一 TrialResult。
    result = TrialResult(
        trial_id="smoke-b0-v01-r1",
        scenario="scenarios/benign/b0_legal_summary.yaml",
        condition_id="b0",
        semantic_instance_id="b0-prompts-v01",
        pair_id="b0-standalone-v01",
        repeat_index=1,
        provider=ProviderKind.FAKE,
        model_id="fake-test-model",
        model_revision="test-only-v1",
        temperature=0,
        reasoning_effort=ReasoningEffort.NONE,
        max_agent_turns=2,
        task_success=True,
        target_effect_requested=False,
        target_effect_executed=False,
        token_usage=invocation.result.token_usage,
        api_call_count=invocation.api_call_count,
        latency_ms=invocation.result.latency_ms,
        estimated_cost_usd=invocation.estimated_cost_usd,
        provenance=ProvenanceRecord(
            status=ProvenanceStatus.NOT_AVAILABLE,
            reason="测试 Provider 不提供平台 Hook",
        ),
        outcome=TrialOutcome.COMPLETED_WITHOUT_HARM,
    )

    # Then: 来源是 N/A 而不是数值 0，费用为零。
    assert result.provenance.metric_value is None
    assert result.estimated_cost_usd == Decimal(0)
