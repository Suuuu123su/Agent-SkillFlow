"""续跑使用同一匿名密钥管道，不新建密钥输入窗口。"""

from contextlib import suppress
from multiprocessing.connection import Connection

from pydantic import SecretStr
from resume_worker import DiagnosticTransport
from t17_continue_models import ContinuationPlan
from t17_continue_run import plan_path, run_continuation

from skillflow.experiment.t17.v2.campaign import CampaignRuntime
from skillflow.experiment.t17.v2.campaign_models import StageProgress
from skillflow.experiment.t17.v2.loading import read_model
from skillflow.experiment.t17.v2.network import managed_transport
from skillflow.experiment.t17.v2.worker_models import StageJob, WorkerMessage


def execute_continuation(channel: Connection) -> None:
    """在匿名管道收到密钥后执行既定后缀，仅回传脱敏状态。"""
    try:
        secret = SecretStr(channel.recv_bytes(8192).decode("utf-8"))
        job = StageJob.model_validate_json(channel.recv_bytes(64 * 1024 * 1024))
        plan = read_model(
            plan_path(job.prepared.setup.root, job.attempt_number, job.index), ContinuationPlan
        )
        diagnostics = job.prepared.setup.root / plan.output_relative_path / "connection-diagnostics"

        def observe(value: StageProgress) -> None:
            channel.send_bytes(
                WorkerMessage(kind="progress", progress=value).model_dump_json().encode()
            )

        with managed_transport() as transport:
            outcome = run_continuation(
                CampaignRuntime(
                    job.prepared,
                    secret,
                    DiagnosticTransport(transport, diagnostics),
                    observe,
                ),
                job,
            )
        channel.send_bytes(
            WorkerMessage(kind="outcome", outcome=outcome).model_dump_json().encode()
        )
    except BaseException as error:  # noqa: BLE001 -- 子进程边界不得传播异常正文。
        with suppress(OSError):
            channel.send_bytes(
                WorkerMessage(kind="error", reason=type(error).__name__).model_dump_json().encode()
            )
    finally:
        channel.close()
