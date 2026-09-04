"""保钥进程只读取项目内的新控制文件，不接收文件形式的 API 密钥。"""

import time
from collections.abc import Callable
from pathlib import Path

from skillflow.experiment.t17.minimal.artifacts import write_checked_json
from skillflow.experiment.t17.v2.loading import read_model
from skillflow.experiment.t17.v2.session_models import (
    CampaignReplacement,
    SessionCommand,
    SessionCommandReceipt,
)

__all__ = ["CampaignReplacement", "SessionCommand", "await_session_command", "read_session_command"]


def read_session_command(control: Path) -> SessionCommand | None:
    """消费结果另外保存，不删除或修改原控制文件。"""
    for path in sorted(control.glob("session-command-*.json")):
        receipt = control / ("receipt-" + path.stem + ".json")
        if receipt.exists():
            continue
        try:
            command = read_model(path, SessionCommand)
        except (ValueError, OSError) as error:
            write_checked_json(
                receipt,
                SessionCommandReceipt(
                    command_id=path.stem,
                    schema_valid=False,
                    reason=type(error).__name__,
                ),
            )
            continue
        write_checked_json(
            receipt, SessionCommandReceipt(command_id=command.command_id, schema_valid=True)
        )
        return command
    return None


def await_session_command(control: Path, notice: Callable[[str], None]) -> SessionCommand:
    """异常后只等待控制，不再次申请密钥，不自动重发请求。"""
    while True:
        try:
            command = read_session_command(control)
            if command is not None:
                return command
            time.sleep(0.5)
        except (OSError, KeyboardInterrupt):
            notice("[保钥暂停] 未发送请求；内存密钥仍在，等待非秘密控制指令。")
            time.sleep(1)
