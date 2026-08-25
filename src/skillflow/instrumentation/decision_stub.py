"""T05 只按 fixture 返回 allow/deny 的决策 seam。"""

from collections.abc import Mapping
from typing import Protocol, assert_never

from skillflow.instrumentation.errors import DecisionFixtureError
from skillflow.models.enums import Decision, EnforcementMode
from skillflow.policy.models import DecisionPlan
from skillflow.policy.runtime import PolicyToolRequest


class DecisionProvider(Protocol):
    """T05 可注入决策 seam。"""

    def evaluate(self, request: PolicyToolRequest) -> DecisionPlan:
        """返回 baseline、policy、authorized 与 executed 的完整计划。"""
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
        """保留 T05 的最小 fixture 查询契约。"""
        try:
            return self._decisions[key]
        except KeyError as error:
            raise DecisionFixtureError(key, "fixture key 未注册") from error

    def evaluate(self, request: PolicyToolRequest) -> DecisionPlan:
        """把 T05 fixture 适配为 monitor 模式的完整计划。"""
        result = self.decide(request.decision_key)
        return DecisionPlan(
            enforcement_mode=EnforcementMode.MONITOR,
            baseline_result=result,
            policy_result=result,
            authorized=False,
            executed=result is Decision.ALLOW,
            manifest_id=None,
            decision_basis_artifact_ids=(request.argument_artifact_id,),
            matched_grant_ids=(),
            reason_codes=("t05_stub_fixture",),
        )
