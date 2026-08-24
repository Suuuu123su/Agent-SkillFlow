import pytest

from skillflow.instrumentation.errors import DecisionFixtureError, ReceiptAuthorityError
from skillflow.instrumentation.tool_proxy import StubDecisionProvider
from skillflow.instrumentation.tool_receipt import ToolReceipt
from skillflow.instrumentation.tool_types import MockToolName
from skillflow.models.enums import Decision


def test_mock_tool_whitelist_excludes_privileged_controls() -> None:
    # Given: T05 普通 Mock Tool 的封闭枚举
    # When: 读取全部可由 Scripted Skill 请求的 Tool 名
    names = frozenset(MockToolName)

    # Then: 只有五个安全适配器，用户确认和 Skill 撤销不在其中
    assert names == {
        MockToolName.READ_FILE,
        MockToolName.WRITE_MEMORY,
        MockToolName.READ_MEMORY,
        MockToolName.HTTP_SEND,
        MockToolName.SHELL_EXEC,
    }


def test_stub_decision_provider_returns_only_fixture_result() -> None:
    # Given: 两个显式 fixture 决策
    provider = StubDecisionProvider(
        {
            "allow-read": Decision.ALLOW,
            "deny-send": Decision.DENY,
        }
    )

    # When: 读取 allow fixture
    result = provider.decide("allow-read")

    # Then: 原样返回 fixture 值，不运行正式授权逻辑
    assert result is Decision.ALLOW


def test_stub_decision_provider_rejects_confirm_and_missing_key() -> None:
    # Given: 一个非法 confirm fixture 和一个空 provider
    # When/Then: Stub 只接受 allow/deny，缺失 key 也显式失败
    with pytest.raises(DecisionFixtureError):
        StubDecisionProvider({"confirm": Decision.CONFIRM})
    with pytest.raises(DecisionFixtureError):
        StubDecisionProvider({}).decide("missing")


def test_tool_receipt_rejects_direct_construction() -> None:
    # Given: Skill 只能看到公开 ToolReceipt 类型
    # When/Then: 直接构造被 API 级签发边界拒绝
    with pytest.raises(ReceiptAuthorityError):
        ToolReceipt()
