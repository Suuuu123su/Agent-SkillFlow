"""DRIFT 的可信动态规则与记忆隔离适配；不删除历史或记忆正文。"""

from dataclasses import replace

from skillflow.defense.task_plan import GateRequest, GateResult, TrustedTaskPlan, matching_nodes
from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.enums import PrincipalType


class QuarantineEntry(StrictModel):
    """记忆键和来源证据的追加隔离记录，不替换授权或数据事实。"""

    run_id: NonEmptyStr
    memory_key: NonEmptyStr
    request_event_id: NonEmptyStr
    source_artifact_ids: tuple[NonEmptyStr, ...]
    reason: NonEmptyStr


class RuleUpdate(StrictModel):
    """可信控制面的规则修订记录，普通内容不能调用这一入口。"""

    issuer: PrincipalType
    event_id: NonEmptyStr
    plan: TrustedTaskPlan


class DynamicRuleMemoryIsolator:
    """每个 Run 独享隔离状态；写入保留证据，后续控制读取被阻止。"""

    def __init__(self) -> None:
        """只维护追加记录，不修改事件库和 Memory 当前头。"""
        self._quarantine: list[QuarantineEntry] = []
        self._updates: list[RuleUpdate] = []

    @property
    def quarantine(self) -> tuple[QuarantineEntry, ...]:
        """返回隔离记录的只读副本。"""
        return tuple(self._quarantine)

    @property
    def rule_updates(self) -> tuple[RuleUpdate, ...]:
        """返回已验证控制主体的规则历史。"""
        return tuple(self._updates)

    def update_rules(self, issuer: PrincipalType, plan: TrustedTaskPlan, event_id: str) -> None:
        """只有用户或可信策略可以修订计划；修订仍不能签发 Grant。"""
        if issuer not in {PrincipalType.USER, PrincipalType.TRUSTED_POLICY}:
            raise ValueError("t18_trusted_rule_issuer_required")
        self._updates.append(RuleUpdate(issuer=issuer, event_id=event_id, plan=plan))

    def evaluate(self, request: GateRequest) -> GateResult:
        """先隔离不可信或撤销来源，再检查动态权限偏离。"""
        key = request.memory_key
        existing = any(
            q.run_id == request.signals.run_id and q.memory_key == key for q in self._quarantine
        )
        tainted = request.memory_untrusted or request.signals.revoked_origin
        if key is not None and tainted and not existing:
            self._quarantine.append(
                QuarantineEntry(
                    run_id=request.signals.run_id,
                    memory_key=key,
                    request_event_id=request.signals.request_event_id,
                    source_artifact_ids=request.memory_artifact_ids,
                    reason="REVOKED_MEMORY"
                    if request.signals.revoked_origin
                    else "UNTRUSTED_MEMORY",
                )
            )
        if request.memory_operation == "read" and (existing or tainted):
            return GateResult(
                action="quarantine",
                reason="MEMORY_CONTROL_ISOLATED",
                evidence_ids=request.signals.evidence_ids,
            )
        if request.signals.revoked_origin and request.memory_operation != "write":
            return GateResult(
                action="quarantine",
                reason="REVOKED_ORIGIN_ISOLATED",
                evidence_ids=request.signals.evidence_ids,
            )
        if not request.authorized:
            return GateResult(
                action="deny",
                reason="DYNAMIC_PERMISSION_DEVIATION",
                evidence_ids=request.signals.evidence_ids,
            )
        if self._updates and not matching_nodes(replace(request, task_plan=self._updates[-1].plan)):
            return GateResult(
                action="deny",
                reason="DYNAMIC_TASK_DEVIATION",
                evidence_ids=(*request.signals.evidence_ids, self._updates[-1].event_id),
            )
        return GateResult(
            action="allow",
            reason="DYNAMIC_RULES_SATISFIED",
            evidence_ids=request.signals.evidence_ids,
        )
