"""同一 Skill 调用内的恢复决策证据，不能当作模型结果重采样。"""

from skillflow.experiment.t17.v2.api_models import CallIdentity
from skillflow.models.base import StrictModel


class RecoveryIntent(StrictModel):
    """只在真实工具阻断后、下一次付费请求之前同步登记。"""

    unit_id: str
    call: CallIdentity
    source_attempt_index: int
    next_attempt_index: int
    blocked_argument_artifact_ids: tuple[str, ...]
    excluded_action_ids: tuple[str, ...]
