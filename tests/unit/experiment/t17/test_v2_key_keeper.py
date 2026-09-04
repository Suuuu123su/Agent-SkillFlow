"""子进程硬退出后重开子进程，密钥仍只输入一次且不写入文件。"""

import hashlib
import os
from multiprocessing.connection import Connection
from pathlib import Path

from pydantic import SecretStr

from skillflow.experiment.t17.v2.key_keeper import MemoryKeyKeeper


def _interrupted_child(channel: Connection) -> None:
    channel.recv_bytes()
    channel.recv_bytes()
    os._exit(23)


def _successful_child(channel: Connection) -> None:
    secret = channel.recv_bytes()
    assert channel.recv_bytes() == b"local-check-only"
    assert secret.decode() not in os.environ.values()
    channel.send_bytes(hashlib.sha256(secret).hexdigest().encode())
    channel.close()


def test_child_hard_exit_does_not_drop_or_reread_key(tmp_path: Path) -> None:
    calls = []

    def reader() -> SecretStr:
        calls.append(1)
        return SecretStr("synthetic-key-kept-only-in-memory")

    keeper = MemoryKeyKeeper(reader())
    replies: list[bytes] = []
    first = keeper.execute(b"local-check-only", _interrupted_child, replies.append)
    second = keeper.execute(b"local-check-only", _successful_child, replies.append)
    assert first.exit_code == 23
    assert second.exit_code == 0
    assert second.reason is None
    assert len(calls) == 1
    assert replies == [hashlib.sha256(b"synthetic-key-kept-only-in-memory").hexdigest().encode()]
    assert "synthetic-key" not in repr(keeper)
    assert list(tmp_path.iterdir()) == []


def test_progress_display_failure_does_not_kill_keeper() -> None:
    keeper = MemoryKeyKeeper(SecretStr("synthetic-key"))

    def bad_display(value: bytes) -> None:
        raise BrokenPipeError

    result = keeper.execute(b"local-check-only", _successful_child, bad_display)
    assert result.exit_code == 0
