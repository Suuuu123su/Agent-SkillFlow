"""非秘密恢复指令只控制已经停止的尝试，不接触 API 密钥。"""

import time
from collections.abc import Callable
from pathlib import Path

from skillflow.experiment.t17.minimal.artifacts import write_checked_json
from skillflow.experiment.t17.v2.campaign_models import StageOutcome
from skillflow.experiment.t17.v2.loading import read_model
from skillflow.experiment.t17.v2.session_commands import read_session_command
from skillflow.experiment.t17.v2.session_models import (
    CommandReceipt,
    ResumeCommand,
    SessionCommandRequestedError,
)


def validate_resume(command: ResumeCommand, outcome: StageOutcome) -> None:
    """只允许整阶段的新尝试，不续填旧目录、不为模型行为重新采样。"""
    if command.raw_relative_path != outcome.raw_relative_path:
        raise ValueError("v2_resume_attempt_binding")
    if command.action == "stop_keep_evidence":
        return
    if outcome.status != "failed" or outcome.reason not in {
        "worker_exit",
        "worker_interrupted",
        "worker_close_timeout",
        "BrokenPipeError",
        "EOFError",
    }:
        raise ValueError("v2_resume_not_infrastructure_interruption")


def await_resume(
    output: Path,
    outcome: StageOutcome,
    notice: Callable[[str], None],
    session_control: Path | None = None,
) -> bool:
    """暂停请求但保持父进程与内存密钥；新指令文件不含任何秘密。"""
    control = output / "control"
    control.mkdir(exist_ok=True)
    while True:
        try:
            if session_control is not None:
                session_command = read_session_command(session_control)
                if session_command is not None:
                    raise SessionCommandRequestedError(session_command)
            for path in sorted(control.glob("command-*.json")):
                receipt_path = control / ("receipt-" + path.stem + ".json")
                if receipt_path.exists():
                    continue
                try:
                    command = read_model(path, ResumeCommand)
                    validate_resume(command, outcome)
                except (ValueError, OSError) as error:
                    write_checked_json(
                        receipt_path,
                        CommandReceipt(
                            command_id=path.stem,
                            accepted=False,
                            reason=type(error).__name__,
                        ),
                    )
                    notice("[暂停] 恢复指令未通过检查；密钥仍在内存中。")
                    continue
                write_checked_json(
                    receipt_path, CommandReceipt(command_id=command.command_id, accepted=True)
                )
                return command.action == "retry_interrupted_stage"
            time.sleep(0.5)
        except KeyboardInterrupt:
            notice("[暂停] 保管进程仍保留密钥；结束请发送 stop_keep_evidence 指令。")
        except OSError:
            notice("[暂停] 控制目录暂时不可读；不发送请求，密钥继续保留。")
            time.sleep(1)
