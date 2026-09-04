"""匿名管道内的阶段任务与安全消息；任务本身不含密钥。"""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from skillflow.experiment.t17.v2.campaign_models import StageOutcome, StageProgress
from skillflow.experiment.t17.v2.campaign_setup import PreparedCampaign
from skillflow.experiment.t17.v2.run_models import PhaseContract
from skillflow.models.base import NonEmptyStr, StrictModel


class StageJob(StrictModel):
    """预算和全部冻结输入来自父进程，子进程仍须在请求前复核。"""

    prepared: PreparedCampaign
    index: Annotated[int, Field(ge=0, le=4)]
    attempt_number: Annotated[int, Field(ge=1)]
    previous: tuple[StageOutcome, ...] = ()
    failed: tuple[StageOutcome, ...] = ()
    approved_phase: PhaseContract

    @model_validator(mode="after")
    def verify_stage_identity(self) -> Self:
        """子进程请求绑定准备时已读入内存的同一批准阶段。"""
        if self.approved_phase != self.prepared.phases[self.index]:
            raise ValueError("v2_worker_approved_phase_binding")
        return self


class WorkerMessage(StrictModel):
    """只转发数量、阶段结果或错误类别，不包含请求正文。"""

    kind: Literal["progress", "outcome", "error"]
    progress: StageProgress | None = None
    outcome: StageOutcome | None = None
    reason: NonEmptyStr | None = None

    @model_validator(mode="after")
    def require_one_payload(self) -> Self:
        """拒绝不明消息，不能把错误解释成成功。"""
        supplied = {
            "progress": self.progress is not None,
            "outcome": self.outcome is not None,
            "error": self.reason is not None,
        }
        if not supplied[self.kind] or sum(supplied.values()) != 1:
            raise ValueError("v2_worker_message_payload")
        return self
