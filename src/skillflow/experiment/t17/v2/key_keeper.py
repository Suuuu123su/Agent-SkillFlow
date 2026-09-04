"""只在父进程内存中保管密钥，通过匿名管道交给单个实验子进程。"""

from collections.abc import Callable
from dataclasses import dataclass, field
from multiprocessing import get_context
from multiprocessing.connection import Connection
from typing import Protocol

from pydantic import SecretStr

_MAX_MESSAGE = 64 * 1024 * 1024


class _PipeReader(Protocol):
    def poll(self, timeout: float = 0.0) -> bool: ...

    def recv_bytes(self, maxlength: int | None = None) -> bytes: ...


@dataclass(frozen=True, slots=True)
class ChildExit:
    """退出结果不含异常正文、请求内容或密钥。"""

    exit_code: int | None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class MemoryKeyKeeper:
    """子进程退出不销毁此对象；父进程关闭或电脑重启仍会失去密钥。"""

    secret: SecretStr = field(repr=False)

    def execute(
        self,
        payload: bytes,
        worker: Callable[[Connection], None],
        on_message: Callable[[bytes], None],
    ) -> ChildExit:
        """启动参数只有匿名管道句柄，密钥不进入参数、环境变量或文件。"""
        context = get_context("spawn")
        parent, child = context.Pipe(duplex=True)
        process = context.Process(target=worker, args=(child,), daemon=True)
        started, reason = False, None
        try:
            process.start()
            started = True
            child.close()
            parent.send_bytes(self.secret.get_secret_value().encode("utf-8"))
            parent.send_bytes(payload)
            _collect_messages(parent, process.is_alive, on_message)
        except KeyboardInterrupt:
            reason = "worker_interrupted"
        except (EOFError, BrokenPipeError):
            # Windows 对正常关闭的匿名管道也可能报告 BrokenPipeError。
            pass
        except (ValueError, OSError) as error:
            reason = type(error).__name__
        finally:
            child.close()
            if started:
                if reason is not None and process.is_alive():
                    process.terminate()
                process.join(timeout=5)
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=5)
                    reason = "worker_close_timeout"
            parent.close()
            exit_code = process.exitcode
            process.close()
        if exit_code != 0 and reason is None:
            reason = "worker_exit"
        return ChildExit(exit_code, reason)


def _collect_messages(
    channel: _PipeReader, is_alive: Callable[[], bool], on_message: Callable[[bytes], None]
) -> None:
    while True:
        if channel.poll(0.25):
            try:
                message = channel.recv_bytes(_MAX_MESSAGE)
            except EOFError:
                return
            try:
                on_message(message)
            except OSError:
                # 可视终端关闭不应销毁密钥或修改实验结果。
                continue
        elif not is_alive():
            return
