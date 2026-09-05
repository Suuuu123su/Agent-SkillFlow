"""可信宿主一次输入密钥，固定 T19 子进程通过匿名管道获取。"""

import argparse
import getpass
import os
import sys
import time
import traceback
from decimal import Decimal
from multiprocessing.connection import Connection
from pathlib import Path

from pydantic import Field, SecretStr

from skillflow.experiment.t17.v2.canonical import model_digest
from skillflow.experiment.t17.v2.key_keeper import MemoryKeyKeeper
from skillflow.experiment.t17.v2.network import managed_transport
from skillflow.experiment.t19.campaign import CampaignSetup, Progress, run_campaign
from skillflow.experiment.t19.freeze import verify_phase
from skillflow.experiment.t19.live import T19LiveClient
from skillflow.experiment.t19.persistence import write_record
from skillflow.experiment.t19.usage import read_usage
from skillflow.models.base import StrictModel


class HostJob(StrictModel):
    """只接受冻结任务目录，无任意命令、网络目的地或模型参数。"""

    root: Path
    live_root: Path
    phase_directory: Path
    output_directory: Path
    attempt_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")


class HostStatus(StrictModel):
    """可公开的监督状态，不保存异常自由正文。"""

    status: str
    reason: str | None = None
    exception_locations: tuple[str, ...] = ()
    api_calls: int = 0
    responses: int = 0
    estimated_cost_usd: Decimal = Decimal(0)
    reserved_cost_usd: Decimal = Decimal(0)


def worker(channel: Connection) -> None:
    """固定目标函数；凭据不进入命令行、环境变量或被测 Agent。"""
    secret = SecretStr(channel.recv_bytes().decode("utf-8"))
    job = HostJob.model_validate_json(channel.recv_bytes())
    status = HostStatus(status="failed", reason="worker_not_started")
    client: T19LiveClient | None = None
    opened = False
    output_permitted = False
    try:
        root = _validate_job(job)
        output_permitted = True
        frozen, plan, config = verify_phase(root, job.phase_directory)
        journals = sorted(job.live_root.glob("attempts/*/api-usage.jsonl"))
        previous = max(
            (
                rows[-1].total_reserved_usd
                for p in journals
                if (rows := read_usage(p, job.live_root))
            ),
            default=Decimal(0),
        )
        journal = job.live_root / "attempts" / job.attempt_id / "api-usage.jsonl"
        with managed_transport(config.endpoint) as transport:
            client = T19LiveClient(config, secret, transport)
            client.open_accounted_journal(journal, model_digest(frozen), previous)
            opened = True

            def progress(item: Progress) -> None:
                usage = client.closed_usage()
                channel.send_bytes(
                    HostStatus(
                        status="running",
                        api_calls=usage.api_calls,
                        responses=usage.responses,
                        estimated_cost_usd=usage.estimated_cost_usd,
                        reserved_cost_usd=usage.reserved_cost_usd,
                    )
                    .model_dump_json()
                    .encode()
                )
                progress_path = job.output_directory / "progress" / (item.current_id + ".json")
                if not progress_path.exists():
                    write_record(progress_path, item)

            run_campaign(CampaignSetup(root, job.output_directory, plan, client, progress))
            status = HostStatus(status="completed")
    except Exception as error:  # noqa: BLE001 -- 宿主只报告异常类型，绝不打印响应或密钥。
        status = HostStatus(
            status="failed",
            reason=type(error).__name__,
            exception_locations=tuple(
                Path(frame.filename).name + ":" + str(frame.lineno)
                for frame in traceback.extract_tb(error.__traceback__)[-5:]
            ),
        )
    if client is not None and opened:
        usage = client.closed_usage()
        status = status.model_copy(
            update={
                "api_calls": usage.api_calls,
                "responses": usage.responses,
                "estimated_cost_usd": usage.estimated_cost_usd,
                "reserved_cost_usd": usage.reserved_cost_usd,
            }
        )
    if output_permitted:
        write_record(job.output_directory / ("host-result-" + job.attempt_id + ".json"), status)
    channel.send_bytes(status.model_dump_json().encode())
    channel.close()


def _validate_job(job: HostJob) -> Path:
    root = job.root.resolve()
    if any(
        not p.resolve().is_relative_to(root)
        for p in (job.live_root, job.phase_directory, job.output_directory)
    ):
        raise ValueError("t19_host_path_outside_project")
    if not job.output_directory.resolve().is_relative_to(job.live_root.resolve()):
        raise ValueError("t19_host_output_outside_live_root")
    return root


def _display(text: str) -> None:
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


def main() -> None:
    """专用交互终端；用户只输入一次，退出前仅内存保管。"""
    parser = argparse.ArgumentParser(description="T19 trusted API credential host")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--live-root", type=Path, required=True)
    args = parser.parse_args()
    root, live_root = args.root.resolve(), args.live_root.resolve()
    if not live_root.is_relative_to(root):
        raise ValueError("t19_host_path_outside_project")
    live_root.mkdir(parents=True, exist_ok=True)
    _display("T19 DS-V4 FLASH: enter key once locally. Input is hidden; no key file is written.")
    keeper = MemoryKeyKeeper(SecretStr(getpass.getpass("API key: ")))
    write_record(
        live_root / ("host-ready-" + str(os.getpid()) + ".json"),
        HostStatus(status="credential_in_memory"),
    )
    _display("Credential held in memory. Waiting for frozen T19 jobs. Keep this window open.")
    while not (live_root / "stop-host").exists():
        for path in sorted((live_root / "jobs").glob("*.json")):
            marker = live_root / "job-results" / path.name
            if marker.exists():
                continue
            job = HostJob.model_validate_json(path.read_text(encoding="utf-8"))
            if job.root.resolve() != root or job.live_root.resolve() != live_root:
                raise ValueError("t19_host_job_scope_mismatch")
            result = keeper.execute(
                job.model_dump_json().encode(),
                worker,
                lambda payload: _display(payload.decode("utf-8")),
            )
            write_record(marker, HostStatus(status="worker_returned", reason=result.reason))
        time.sleep(1)
    _display("T19 host stopped; in-memory credential released when this process exits.")


if __name__ == "__main__":
    main()
