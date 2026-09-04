"""父进程持钥、子进程实验；暂停和恢复均不要求再次输入密钥。"""

from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path

from skillflow.experiment.t17.minimal.artifacts import write_checked_json
from skillflow.experiment.t17.v2.campaign import campaign_result
from skillflow.experiment.t17.v2.campaign_models import CampaignResult, StageOutcome, StageProgress
from skillflow.experiment.t17.v2.campaign_setup import PreparedCampaign, claim_campaign
from skillflow.experiment.t17.v2.interruption import interrupted_outcome
from skillflow.experiment.t17.v2.key_keeper import MemoryKeyKeeper
from skillflow.experiment.t17.v2.stage_worker import execute_stage
from skillflow.experiment.t17.v2.supervisor_control import await_resume
from skillflow.experiment.t17.v2.worker_models import StageJob, WorkerMessage


@dataclass(slots=True)
class WorkerInbox:
    """安全消息收件箱；显示失败不能影响结果或父进程存活。"""

    observer: Callable[[StageProgress], None]
    outcomes: list[StageOutcome] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def receive(self, raw: bytes) -> None:
        """一次子进程最多产生一个阶段结论。"""
        message = WorkerMessage.model_validate_json(raw)
        if message.progress is not None:
            with suppress(OSError):
                self.observer(message.progress)
        if message.outcome is not None:
            self.outcomes.append(message.outcome)
        if message.reason is not None:
            self.errors.append(message.reason)


def run_supervised(
    prepared: PreparedCampaign,
    keeper: MemoryKeyKeeper,
    observer: Callable[[StageProgress], None],
    notice: Callable[[str], None],
    session_control: Path | None = None,
) -> CampaignResult:
    """门未通过就停请求；保管进程继续等待非秘密指令，不自动重采样。"""
    output = prepared.setup.output
    claim = claim_campaign(prepared)
    output.mkdir(parents=True, exist_ok=False)
    write_checked_json(output / "campaign-contract.json", claim)
    write_checked_json(output / "approved-cost-plan.json", prepared.plan)
    passed: list[StageOutcome] = []
    failed: list[StageOutcome] = []
    while len(passed) < len(prepared.matrices):
        index = len(passed)
        attempt_number = 1 + sum(s.stage == prepared.matrices[index].stage for s in failed)
        job = StageJob(
            prepared=prepared,
            index=index,
            attempt_number=attempt_number,
            previous=tuple(passed),
            failed=tuple(failed),
            approved_phase=prepared.phases[index],
        )
        outcome = run_stage_process(job, keeper, observer)
        (passed if outcome.status == "passed" else failed).append(outcome)
        result = campaign_result(prepared, tuple(passed), failed=tuple(failed))
        write_checked_json(
            output / f"campaign-after-attempt-{len(passed) + len(failed):03d}.json", result
        )
        if outcome.status == "passed":
            notice("[阶段完成] " + outcome.stage.value + "；已保留完整数据与费用记录。")
            continue
        notice("[暂停] 本次尝试未通过，停止后续 API；密钥仍在保管进程内，不必重输。")
        if not await_resume(output, outcome, notice, session_control):
            break
    result = campaign_result(prepared, tuple(passed), failed=tuple(failed))
    write_checked_json(output / "campaign-result.json", result)
    return result


def run_stage_process(
    job: StageJob, keeper: MemoryKeyKeeper, observer: Callable[[StageProgress], None]
) -> StageOutcome:
    """即使子进程被强制关闭，父进程也保存中断证据并保留密钥。"""
    inbox = WorkerInbox(observer)
    exited = keeper.execute(job.model_dump_json().encode(), execute_stage, inbox.receive)
    if (
        exited.exit_code == 0
        and exited.reason is None
        and not inbox.errors
        and len(inbox.outcomes) == 1
    ):
        return inbox.outcomes[0]
    reason = inbox.errors[0] if inbox.errors else (exited.reason or "worker_exit")
    return interrupted_outcome(job, reason)
