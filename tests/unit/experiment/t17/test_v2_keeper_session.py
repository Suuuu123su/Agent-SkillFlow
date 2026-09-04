"""父监督自身异常也不能让用户重复输入密钥。"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pydantic import SecretStr

from skillflow.experiment.t17.v2 import keeper_session
from skillflow.experiment.t17.v2.campaign_setup import PreparedCampaign
from skillflow.experiment.t17.v2.key_keeper import MemoryKeyKeeper
from skillflow.experiment.t17.v2.session_commands import CampaignReplacement, SessionCommand


def test_supervisor_exception_keeps_the_same_key_for_approved_replacement(
    t17_cli_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    initial = MagicMock(spec=PreparedCampaign)
    initial.setup.root = Path.cwd()
    replacement = MagicMock(spec=PreparedCampaign)
    keeper = MemoryKeyKeeper(SecretStr("synthetic-session-key"))
    seen = []

    def run(prepared: PreparedCampaign, held: MemoryKeyKeeper, *args: object) -> None:
        seen.append(held)
        if len(seen) == 1:
            raise OSError

    command = SessionCommand(
        command_id="switch-approved-plan",
        action="start_approved_campaign",
        replacement=CampaignReplacement(
            protocol="new/protocol",
            cost_plan="new/cost.json",
            approval="new/approval.json",
            output="new/output",
        ),
    )
    monkeypatch.setattr(keeper_session, "run_supervised", run)
    monkeypatch.setattr(keeper_session, "await_session_command", lambda *args: command)
    monkeypatch.setattr(keeper_session, "prepare_campaign", lambda setup: replacement)
    keeper_session.run_key_session(initial, keeper, lambda _: None, lambda _: None, t17_cli_root)
    assert len(seen) == 2
    assert all(value is keeper for value in seen)
