"""保钥会话的非秘密控制格式，不含任何凭据保存选项。"""

from typing import Literal, Self

from pydantic import model_validator

from skillflow.experiment.t17.v2.frozen import FrozenFile
from skillflow.models.base import NonEmptyStr, StrictModel


class ResumeCommand(StrictModel):
    """绑定失败目录，不能用陈旧指令恢复后来失败或重采样模型结果。"""

    command_id: NonEmptyStr
    action: Literal["retry_interrupted_stage", "stop_keep_evidence"]
    raw_relative_path: NonEmptyStr


class CommandReceipt(StrictModel):
    """保留指令原件与接受结果，不通过删除消费指令。"""

    command_id: NonEmptyStr
    accepted: bool
    reason: NonEmptyStr | None = None


class InterruptionManifest(StrictModel):
    """已有终态与新增中断记录分别登记，不能用于宣称阶段完成。"""

    schema_version: Literal["2.0"] = "2.0"
    phase_contract_sha256: NonEmptyStr
    reason: NonEmptyStr
    scheduled_core: int
    scheduled_replay: int
    preserved_terminals: tuple[NonEmptyStr, ...]
    interrupted_terminals: tuple[NonEmptyStr, ...]
    files: dict[NonEmptyStr, FrozenFile]
    stage_passed: Literal[False] = False


class CampaignReplacement(StrictModel):
    """协议修订必须指向全新的已批准配置，旧批准不能重复消费。"""

    protocol: NonEmptyStr
    cost_plan: NonEmptyStr
    approval: NonEmptyStr
    output: NonEmptyStr


class SessionCommand(StrictModel):
    """重新批准计划或明确结束保钥，不授予额外费用权限。"""

    command_id: NonEmptyStr
    action: Literal["start_approved_campaign", "stop_keep_evidence"]
    replacement: CampaignReplacement | None = None

    @model_validator(mode="after")
    def require_replacement(self) -> Self:
        """新计划路径只允许与相应指令一起出现。"""
        if (self.action == "start_approved_campaign") != (self.replacement is not None):
            raise ValueError("v2_session_command_fields")
        return self


class SessionCommandReceipt(StrictModel):
    """只确认控制文件已读；不冒充费用批准或实验完成。"""

    command_id: NonEmptyStr
    schema_valid: bool
    reason: NonEmptyStr | None = None
    grants_api_authorization: Literal[False] = False


class SessionCommandRequestedError(RuntimeError):
    """把非秘密控制交还最外层持钥循环，不退出进程。"""

    def __init__(self, command: SessionCommand) -> None:
        """不在异常字符串中展示控制文件内容。"""
        super().__init__("v2_session_control_requested")
        self.command = command
