"""T05 只按 fixture 返回 allow/deny 的决策 seam。"""

from collections.abc import Mapping
from typing import Protocol, assert_never

from skillflow.instrumentation.errors import DecisionFixtureError
from skillflow.models.enums import Decision


class DecisionProvider(Protocol):
    """T05 可注入决策 seam。"""

    def decide(self, key: str) -> Decision:
        """按 fixture key 返回 allow/deny。"""
        ...


class StubDecisionProvider:
    """只按 fixture key 返回 allow/deny 的临时决策器。"""

    def __init__(self, decisions: Mapping[str, Decision]) -> None:
        """复制并验证仅含 allow/deny 的 fixture。"""
        for key, decision in decisions.items():
            match decision:
                case Decision.ALLOW | Decision.DENY:
                    pass
                case Decision.CONFIRM:
                    raise DecisionFixtureError(key, "T05 Stub 只接受 allow/deny")
                case _ as unreachable:
                    assert_never(unreachable)
        self._decisions = dict(decisions)

    def decide(self, key: str) -> Decision:
        """返回 fixture 中预先声明的决定。"""
        try:
            return self._decisions[key]
        except KeyError as error:
            raise DecisionFixtureError(key, "fixture key 未注册") from error
