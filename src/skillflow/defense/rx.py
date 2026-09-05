"""T19 请求级动态选择；在线输入不包含评测真值或未来执行结果。"""

from typing import Literal

from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.effects import CapabilityEffect

Component = Literal["T", "P", "M"]
TreatmentName = Literal["Monitor", "Grant-only", "Best Fixed", "All", "Evidence", "Coarse"]
ORDER: tuple[Component, ...] = ("T", "P", "M")


class TaskPermission(StrictModel):
    """可信用户目标允许的操作集合；不限定唯一动作序列。"""

    actor_id: NonEmptyStr
    session_ids: tuple[NonEmptyStr, ...]
    effect: CapabilityEffect
    evidence_id: NonEmptyStr


class TaskConstraints(StrictModel):
    """在读取技能之前签发，不从风险评分器或目标轨迹导出。"""

    issuer: Literal["trusted_user_task"] = "trusted_user_task"
    contract_id: NonEmptyStr
    permissions: tuple[TaskPermission, ...]

    def permits(self, actor: str, session: str, effect: CapabilityEffect) -> bool:
        """允许集合内的任意合法顺序，重复动作仍须经过资源预算检查。"""
        return any(
            p.actor_id == actor and session in p.session_ids and p.effect == effect
            for p in self.permissions
        )


class SourceEvidence(StrictModel):
    """实际请求的一个来源/版本；数据权限和指令权限显式分开。"""

    artifact_id: NonEmptyStr
    producer_event_id: NonEmptyStr
    channel: Literal["user", "skill", "tool", "memory", "unknown"]
    instruction_authority: bool
    revoked: bool
    memory_key: str | None = None
    memory_version_id: str | None = None
    evidence_ids: tuple[NonEmptyStr, ...]


class RequestEvidence(StrictModel):
    """执行前的封闭证据投影；不接收原始场景对象或通用字典。"""

    request_id: NonEmptyStr
    actor_id: NonEmptyStr
    session_id: NonEmptyStr
    effect: CapabilityEffect
    grant_authorized: bool
    task_permitted: bool
    sources: tuple[SourceEvidence, ...]
    provenance_complete: bool
    authorization_complete: bool
    evidence_ids: tuple[NonEmptyStr, ...]


class Selection(StrictModel):
    """选择器只指定共享组件及其干预边界，不签发授权。"""

    components: tuple[Component, ...]
    abstain: bool
    reasons: tuple[NonEmptyStr, ...]
    evidence_ids: tuple[NonEmptyStr, ...]


class Intervention(StrictModel):
    """请求阻断不改写授权；无法分离的条目不会被宣称净化。"""

    component: Component
    action: Literal["allow", "deny", "confirm"]
    request_id: NonEmptyStr
    artifact_ids: tuple[NonEmptyStr, ...]
    memory_versions: tuple[NonEmptyStr, ...]
    reason: NonEmptyStr
    evidence_ids: tuple[NonEmptyStr, ...]


def select(evidence: RequestEvidence, *, coarse: bool = False) -> Selection:
    """Coarse 仅屏蔽选择特征，不改共享组件能看到的完整证据。"""
    selected: set[Component] = set()
    reasons: list[str] = []
    if not evidence.task_permitted:
        selected.add("T")
        reasons.append("OUTSIDE_TRUSTED_TASK")
    if not coarse:
        if any(not s.instruction_authority for s in evidence.sources):
            selected.add("P")
            reasons.append("DATA_IS_NOT_INSTRUCTION_AUTHORITY")
        if any(s.revoked and s.channel == "memory" for s in evidence.sources):
            selected.add("M")
            reasons.append("REVOKED_MEMORY_VERSION")
    missing = not evidence.provenance_complete or not evidence.authorization_complete
    if missing:
        reasons.append("EVIDENCE_INCOMPLETE")
    return Selection(
        components=tuple(c for c in ORDER if c in selected),
        abstain=missing,
        reasons=tuple(reasons),
        evidence_ids=evidence.evidence_ids,
    )


def evaluate(component: Component, evidence: RequestEvidence) -> Intervention:
    """所有模式调用相同实现；低可信数据可用于可信任务。"""
    targets: tuple[SourceEvidence, ...] = ()
    action: Literal["allow", "deny", "confirm"] = "allow"
    reason = "TRUSTED_TASK_DATA_ALLOWED"
    if component == "T" and not evidence.task_permitted:
        action, reason = "deny", "OUTSIDE_TRUSTED_TASK"
    elif component == "P":
        targets = tuple(s for s in evidence.sources if not s.instruction_authority)
        if targets and not evidence.task_permitted:
            action, reason = "deny", "SOURCE_CANNOT_AUTHORIZE_ADDITIONAL_ACTION"
        elif not evidence.provenance_complete and not evidence.task_permitted:
            action, reason = "confirm", "UNRESOLVED_SOURCE_FOR_ADDITIONAL_ACTION"
    elif component == "M":
        targets = tuple(s for s in evidence.sources if s.revoked and s.channel == "memory")
        if targets and not evidence.task_permitted:
            action, reason = "deny", "REVOKED_MEMORY_CONTROL_REQUEST"
    return Intervention(
        component=component,
        action=action,
        request_id=evidence.request_id,
        artifact_ids=tuple(s.artifact_id for s in targets),
        memory_versions=tuple(
            s.memory_version_id for s in targets if s.memory_version_id is not None
        ),
        reason=reason,
        evidence_ids=evidence.evidence_ids,
    )


def intervene(selection: Selection, evidence: RequestEvidence) -> tuple[Intervention, ...]:
    """冻结 T/P/M 顺序及首个非放行短路规则。"""
    results = []
    for component in ORDER:
        if component not in selection.components:
            continue
        result = evaluate(component, evidence)
        results.append(result)
        if result.action != "allow":
            break
    return tuple(results)
