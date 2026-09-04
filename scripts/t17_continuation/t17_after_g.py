"""后台衔接既定 G→H；只查看结果文件，不持有密钥，不扩展实验。"""

import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from t17_prepare_defense import APPROVAL, OUTPUT, PLAN, PROTOCOL, main, prerequisite_paths

from skillflow.experiment.t17.minimal.artifacts import write_checked_json
from skillflow.experiment.t17.v2.session_models import CampaignReplacement, SessionCommand

ROOT = Path(__file__).resolve().parents[2]
CONTROL = ROOT / ".tmp/t17-luna-defense-20260904-01/control"
STATUS = ROOT / ".tmp/t17-luna-defense-20260904-01/handoff-status.json"
COMMAND = CONTROL / "session-command-start-h-01.json"
RECEIPT = CONTROL / "receipt-session-command-start-h-01.json"


def status(state: str, reason: str | None = None) -> None:
    """写入无密钥的显示状态，不修改实际运行证据。"""
    # 可覆盖状态只用于显示；实际批准、命令、回执和原始记录均独占保存。
    STATUS.write_text(
        json.dumps(
            {
                "state": state,
                "reason": reason,
                "updated_at": datetime.now(UTC).isoformat(),
                "key_accessed_by_watcher": False,
            }
        ),
        encoding="utf-8",
    )


def run() -> None:
    """旧衔接入口保留停止标记与幂等派发限制。"""
    if COMMAND.exists():
        status("already_dispatched_no_duplicate")
        return
    status("waiting_for_G_passed")
    while True:
        if (CONTROL / "stop-handoff.json").exists():
            status("stopped_before_dispatch")
            return
        try:
            prerequisite_paths()
        except ValueError as error:
            if str(error) != "defense_waiting_for_complete_G":
                raise
            time.sleep(15)
            continue
        if not (CONTROL / "key-received.json").is_file():
            status("waiting_for_luna_key")
            time.sleep(15)
            continue
        break
    status("preparing_H_after_G_passed")
    main()
    command = SessionCommand(
        command_id="t17-luna-H-after-deepseek-G-20260904",
        action="start_approved_campaign",
        replacement=CampaignReplacement(
            protocol=PROTOCOL, cost_plan=PLAN, approval=APPROVAL, output=OUTPUT
        ),
    )
    write_checked_json(COMMAND, command)
    # 只记录是否收到命令，不把收到命令或启动窗口记作实验成功。
    for _ in range(20):
        if RECEIPT.is_file():
            status("H_command_received")
            return
        time.sleep(3)
    status("H_command_written_receipt_not_yet_observed")


if __name__ == "__main__":
    try:
        run()
    except BaseException as error:  # noqa: BLE001 -- 进程边界只记录异常类型。
        status("handoff_paused", type(error).__name__)
        sys.exit(1)
