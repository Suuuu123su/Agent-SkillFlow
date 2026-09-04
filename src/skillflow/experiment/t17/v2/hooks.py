"""第二版把空决策结果与缺少测量能力区分开。"""

from skillflow.experiment.t17.contracts import HookCapability, HookName, MeasurementStatus
from skillflow.experiment.t17.minimal.task_models import NormalTaskEvidence
from skillflow.experiment.t17.observation_models import ReferenceObservationSnapshot
from skillflow.models.enums import EventType
from skillflow.models.events import SecurityEvent


def measured_hooks(
    runtime: ReferenceObservationSnapshot,
    task: NormalTaskEvidence,
    events: tuple[SecurityEvent, ...],
) -> tuple[HookCapability, ...]:
    """完整事件日志可证明零工具请求；不制造决策、权限或回执。"""
    requests = tuple(e.event_id for e in events if e.event_type is EventType.TOOL_CALL_REQUEST)
    ended = tuple(e.event_id for e in events if e.event_type is EventType.SESSION_END)
    decisions = tuple(d.decision_id for d in runtime.decisions)
    hooks = []
    for hook in runtime.hooks:
        if hook.hook is HookName.TASK_SUCCESS:
            hooks.append(
                HookCapability(
                    hook=hook.hook,
                    required=True,
                    available=True,
                    status=MeasurementStatus.MEASURED,
                    evidence_ids=task.evidence_ids,
                )
            )
        elif (
            hook.required
            and hook.hook is HookName.DECISION_BASIS
            and (decisions or (not requests and ended))
        ):
            # 决策的依据列表为空也是受信观察；无请求时由完整会话日志证明零次。
            hooks.append(
                HookCapability(
                    hook=hook.hook,
                    required=True,
                    available=True,
                    status=MeasurementStatus.MEASURED,
                    evidence_ids=decisions or ended,
                )
            )
        else:
            hooks.append(hook)
    return tuple(hooks)
