"""T17 Live Supervisor 的非秘密阶段确认与安全终端输出。"""

from pathlib import Path

import typer

from skillflow.experiment.t17.budget_proposal import (
    T17BudgetProposal,
    build_followup_budget_proposal,
    write_budget_proposal,
)
from skillflow.experiment.t17.live_matrix import (
    T17LiveStage,
    load_live_matrix,
)
from skillflow.experiment.t17.live_stage_support import (
    T17LiveProgressEvent,
    T17LiveProgressSink,
)
from skillflow.experiment.t17.live_supervisor import (
    STAGE_MATRIX_FILENAMES,
    T17ConfirmedBudgetProposal,
    T17LiveSupervisor,
    T17SupervisorStageResult,
    load_and_confirm_budget_proposal,
    read_t17_api_key,
)

NEXT_STAGE = {
    T17LiveStage.CANARY: T17LiveStage.MODEL1,
    T17LiveStage.MODEL1: T17LiveStage.MODEL2_CANARY,
    T17LiveStage.MODEL2_CANARY: T17LiveStage.MODEL2,
    T17LiveStage.MODEL2: T17LiveStage.DEFENSE,
}


class T17ConsoleProgress(T17LiveProgressSink):
    """只显示计数、失败、Token 与费用，不显示正文。"""

    def __call__(self, event: T17LiveProgressEvent) -> None:
        """输出一条适合终端轮询的安全进度。"""
        typer.echo(
            f"[T17 Live] complete={event.completed_units}/{event.scheduled_units} "
            f"failed={event.failed_units} calls={event.api_call_count} "
            f"tokens={event.total_tokens} actual_est_usd={event.estimated_cost_usd} "
            f"reserved_usd={event.conservative_reserved_usd}"
        )


def run_live_supervisor_cli(
    project_root: Path,
    campaign_root: Path,
    initial_stage: T17LiveStage,
    initial_proposal_path: Path,
) -> tuple[T17SupervisorStageResult, ...]:
    """预算确认后隐藏读取一次密钥，并允许同进程继续后续阶段。"""
    root = project_root.resolve()
    campaign = campaign_root.resolve()
    stage = initial_stage
    proposal_path = initial_proposal_path.resolve()
    _require_new_campaign_root(campaign)
    confirmed = _load_and_confirm_proposal(stage, proposal_path)
    if confirmed is None:
        raise typer.Abort
    campaign.mkdir(parents=True, exist_ok=False)
    api_key = read_t17_api_key()
    supervisor = T17LiveSupervisor(root, campaign, api_key)
    try:
        while True:
            result = supervisor.run_confirmed_stage(
                confirmed,
                T17ConsoleProgress(),
            )
            _print_stage_result(result)
            if (
                not result.result.summary.live_gate_passed
                or not result.metrics.required_metrics_complete
            ):
                return supervisor.results
            next_stage = NEXT_STAGE.get(stage)
            if next_stage is None:
                return supervisor.results
            proposal_path = campaign / "budget-proposals" / f"{next_stage.value}.json"
            target_matrix = load_live_matrix(
                root / "experiments" / "t17" / STAGE_MATRIX_FILENAMES[next_stage]
            )
            next_proposal = build_followup_budget_proposal(
                result.prepared.attempt_root,
                target_matrix,
            )
            write_budget_proposal(proposal_path, next_proposal)
            next_confirmed = _load_and_confirm_proposal(
                next_stage,
                proposal_path,
            )
            if next_confirmed is None:
                return supervisor.results
            stage = next_stage
            confirmed = next_confirmed
    finally:
        del api_key


def _load_and_confirm_proposal(
    stage: T17LiveStage,
    proposal_path: Path,
) -> T17ConfirmedBudgetProposal | None:
    def confirm(proposal: T17BudgetProposal) -> bool:
        if proposal.stage is not stage:
            detail = f"预算提案阶段为 {proposal.stage.value}，不是 {stage.value}"
            raise typer.BadParameter(detail)
        typer.echo(
            f"[预算提案] stage={stage.value} model={proposal.model_revision} "
            f"core={proposal.scheduled_core_trials} "
            f"replay={proposal.scheduled_replay_pairs} "
            f"projected_usd={proposal.projected_actual_usd} "
            f"conservative_usd={proposal.conservative_projected_usd} "
            f"hard_total_usd={proposal.requested_max_total_usd} "
            f"hard_run_usd={proposal.requested_max_cost_per_run_usd} "
            "calls_made=0"
        )
        return typer.confirm(
            "是否明确批准这一阶段的费用硬门?",
            default=False,
        )

    return load_and_confirm_budget_proposal(proposal_path, confirm)


def _print_stage_result(result: T17SupervisorStageResult) -> None:
    summary = result.result.summary
    typer.echo(
        f"[阶段完成] stage={summary.stage.value} gate={summary.live_gate_passed} "
        f"core={summary.completed_core_trials}/{summary.scheduled_core_trials} "
        f"replay={summary.completed_replay_pairs}/{summary.scheduled_replay_pairs} "
        f"calls={summary.telemetry.api_call_count} "
        f"tokens={summary.telemetry.token_usage.model_dump_json()} "
        f"actual_est_usd={summary.telemetry.estimated_cost_usd} "
        f"reserved_usd={summary.telemetry.conservative_reserved_usd} "
        f"metrics_complete={result.metrics.required_metrics_complete} "
        f"summary={result.prepared.attempt_root / 'live-summary.json'} "
        f"metrics={result.prepared.attempt_root / 'phase-metrics.json'}"
    )


def _require_new_campaign_root(path: Path) -> None:
    if path.exists():
        detail = f"Campaign 输出已存在: {path.name}"
        raise typer.BadParameter(detail)
