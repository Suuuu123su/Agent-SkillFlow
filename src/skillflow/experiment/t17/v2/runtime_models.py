"""第二版每次模型决定和未执行步骤的非秘密证据。"""

from dataclasses import dataclass, field
from typing import Literal

from skillflow.benchmark.replay_models import ReplaySourceState
from skillflow.models.base import NonEmptyStr, StrictModel

ModelBehavior = Literal["normal", "refusal", "no_call", "schema_rejection"]


class ModelOutcomeError(ValueError):
    """已经保存用量的模型输出失败，不能据此重采样。"""

    def __init__(self, behavior: ModelBehavior) -> None:
        """只保存封闭分类，不保存模型正文。"""
        super().__init__(behavior)
        self.behavior = behavior


class ExecutionIssue(StrictModel):
    """受信步骤编排器记录的输入缺失，不冒充基础设施错误。"""

    run_id: NonEmptyStr
    session_id: NonEmptyStr
    step_id: NonEmptyStr
    reason: Literal["missing_input", "memory_not_present"]
    references: tuple[NonEmptyStr, ...]


class DecisionFact(StrictModel):
    """动作选择记录；没有权限、来源和回执自报字段。"""

    run_id: NonEmptyStr
    session_id: NonEmptyStr
    step_id: NonEmptyStr
    call_id: NonEmptyStr
    implementation: NonEmptyStr
    allowed_action_ids: tuple[NonEmptyStr, ...]
    selected_action_ids: tuple[NonEmptyStr, ...]
    behavior: ModelBehavior
    schema_valid: bool


@dataclass(slots=True)
class RunCapture:
    """单个实际 Run 的独立上下文，包括回放源和两个分支。"""

    run_id: str
    session_id: str = "unstarted"
    step_id: str = "unstarted"
    decisions: list[DecisionFact] = field(default_factory=list)
    issues: list[ExecutionIssue] = field(default_factory=list)
    capture_checkpoints: bool = True
    checkpoints: dict[str, ReplaySourceState] = field(default_factory=dict, repr=False)
