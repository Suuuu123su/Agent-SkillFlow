"""独立实验子进程；它退出不会销毁父进程保存的密钥。"""

from contextlib import suppress
from multiprocessing.connection import Connection

from pydantic import SecretStr

from skillflow.experiment.t17.v2.campaign import CampaignRuntime, run_one_stage
from skillflow.experiment.t17.v2.campaign_models import StageProgress
from skillflow.experiment.t17.v2.worker_models import StageJob, WorkerMessage


def execute_stage(channel: Connection) -> None:
    """密钥从匿名管道读取，不从启动参数、环境或文件中读取。"""
    try:
        secret = SecretStr(channel.recv_bytes(8192).decode("utf-8"))
        job = StageJob.model_validate_json(channel.recv_bytes(64 * 1024 * 1024))
        from skillflow.experiment.t17.v2.network import (  # noqa: PLC0415 -- 只有获批子进程加载网络。
            managed_transport,
        )

        def observe(value: StageProgress) -> None:
            channel.send_bytes(
                WorkerMessage(kind="progress", progress=value).model_dump_json().encode()
            )

        with managed_transport() as transport:
            outcome = run_one_stage(
                CampaignRuntime(job.prepared, secret, transport, observe),
                job.index,
                job.previous,
                attempt_number=job.attempt_number,
                failed=job.failed,
            )
        channel.send_bytes(
            WorkerMessage(kind="outcome", outcome=outcome).model_dump_json().encode()
        )
    except BaseException as error:  # noqa: BLE001 -- 不将异常正文或密钥写到父进程控制台。
        with suppress(OSError):
            channel.send_bytes(
                WorkerMessage(kind="error", reason=type(error).__name__).model_dump_json().encode()
            )
    finally:
        channel.close()
