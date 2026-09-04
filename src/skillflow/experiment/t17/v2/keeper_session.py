"""最外层持钥循环：监督代码异常也保留密钥，直到明确结束或实验完成。"""

from collections.abc import Callable
from pathlib import Path

from skillflow.experiment.t17.v2.campaign_models import CampaignResult, StageProgress
from skillflow.experiment.t17.v2.campaign_setup import (
    CampaignSetup,
    PreparedCampaign,
    prepare_campaign,
)
from skillflow.experiment.t17.v2.canonical import canonical_digest
from skillflow.experiment.t17.v2.frozen import inside
from skillflow.experiment.t17.v2.key_keeper import MemoryKeyKeeper
from skillflow.experiment.t17.v2.session_commands import await_session_command
from skillflow.experiment.t17.v2.session_models import SessionCommand, SessionCommandRequestedError
from skillflow.experiment.t17.v2.supervisor import run_supervised


def create_session_control(root: Path, output: Path) -> Path:
    """在输入密钥之前确认非秘密控制目录可创建，避免初始化失败丢失密钥。"""
    relative = output.resolve().relative_to(root.resolve()).as_posix()
    control = inside(root, "runs/t17-v2-key-sessions/" + canonical_digest(relative))
    control.mkdir(parents=True, exist_ok=False)
    return control


def run_key_session(
    initial: PreparedCampaign,
    keeper: MemoryKeyKeeper,
    observer: Callable[[StageProgress], None],
    notice: Callable[[str], None],
    control: Path,
) -> CampaignResult | None:
    """改变协议须重新检查批准文件；失败原件及原额度均不能重用或清零。"""
    current: PreparedCampaign | None = initial
    command: SessionCommand | None = None
    root = initial.setup.root
    while True:
        if current is not None:
            try:
                return run_supervised(current, keeper, observer, notice, control)
            except SessionCommandRequestedError as request:
                command = request.command
            except (Exception, KeyboardInterrupt) as error:  # noqa: BLE001 -- 最外层必须保钥而非退出。
                notice("[保钥暂停] 监督异常 " + type(error).__name__ + "；不发送后续请求。")
            current = None
        if command is None:
            command = await_session_command(control, notice)
        if command.action == "stop_keep_evidence":
            return None
        replacement = command.replacement
        if replacement is None:
            raise ValueError("v2_session_replacement_required")
        try:
            current = prepare_campaign(
                CampaignSetup(
                    root,
                    inside(root, replacement.output),
                    inside(root, replacement.protocol),
                    inside(root, replacement.cost_plan),
                    inside(root, replacement.approval),
                )
            )
        except (ValueError, OSError):
            notice("[保钥暂停] 新计划尚未通过完整准备或费用批准检查；密钥未丢失。")
        command = None
