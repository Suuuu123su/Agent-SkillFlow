"""只在基础设施中断时推进到首个未完成任务组，不重新采样模型行为失败。"""

from pathlib import Path

from t17_continue_models import ContinuationPlan, SourceIndex, source_unit, terminal_path
from t17_continue_run import plan_path

from skillflow.experiment.t17.minimal.artifacts import write_checked_json
from skillflow.experiment.t17.v2.campaign import partial_usage
from skillflow.experiment.t17.v2.campaign_models import (
    CampaignResult,
    StageBudgetProposal,
    StageOutcome,
)
from skillflow.experiment.t17.v2.frozen import inside
from skillflow.experiment.t17.v2.loading import read_model
from skillflow.experiment.t17.v2.run_models import CoreTerminal, ReplayTerminal
from skillflow.experiment.t17.v2.worker_models import StageJob

MODEL2_INDEX = 3
DEFENSE_INDEX = 4


def first_unfinished(root: Path, index: SourceIndex) -> int | None:
    """按预定序号找第一个缺少完整任务组的断点。"""
    for source in sorted(index.units, key=lambda s: (s.ordinal, s.kind)):
        model = CoreTerminal if source.kind == "core" else ReplayTerminal
        terminal = read_model(terminal_path(root, source), model)
        if terminal.status not in {"completed", "not_applicable"} or not terminal.usage.complete:
            return source.ordinal
    return None


def consecutive_no_progress(starts: tuple[int, ...], ordinal: int) -> int:
    """统计末尾连续停在相同断点的次数。"""
    count = 0
    for start in reversed(starts):
        if start != ordinal:
            break
        count += 1
    return count


def next_continuation(job: StageJob, outcome: StageOutcome, snapshot: Path) -> bool:
    """已通过阶段、协议、绑定、预算或确定性模型错误绝不触发重采样。"""
    gate = outcome.gate
    if (
        gate is None
        or not gate.infrastructure_invalid
        or gate.protocol_errors
        or gate.binding_failures
        or outcome.usage.missing_reason
        not in {
            "network_response_state_unknown",
            "timeout",
            "provider_error",
        }
    ):
        return False
    root = job.prepared.setup.root
    old_path = plan_path(root, job.attempt_number, job.index)
    if old_path.exists():
        old = read_model(old_path, ContinuationPlan)
        directory = inside(root, old.output_relative_path)
        selected_path = directory / "selected-sources.json"
        selected = read_model(selected_path, SourceIndex)
    elif job.index == DEFENSE_INDEX:
        matrix = job.prepared.matrices[job.index]
        directory = inside(root, outcome.raw_relative_path).parent
        old = ContinuationPlan(
            source_raw=outcome.raw_relative_path,
            output_relative_path=directory.relative_to(root).as_posix(),
            snapshot_relative_path=snapshot.relative_to(root).as_posix(),
            first_ordinal=1,
            first_trial_id=matrix.trials[0].trial_id,
            user_instruction="之后如果也出错也这样从断点续跑",
        )
        units = []
        for number, trial in enumerate(matrix.trials, 1):
            units.append(source_unit(root, directory / "raw", number, "core", trial.trial_id))
            units.extend(
                source_unit(root, directory / "raw", number, "replay", identifier)
                for identifier in trial.replay_pair_ids.values()
            )
        selected = SourceIndex(plan=old, units=tuple(units))
        selected_path = directory / "continuation-source-selection.json"
        write_checked_json(selected_path, selected)
    else:
        return False
    ordinal = first_unfinished(root, selected)
    if ordinal is None:
        return False
    state = read_model(snapshot, CampaignResult)
    starts = []
    for previous in reversed(state.failed_attempts):
        prior_plan = inside(root, previous.raw_relative_path).parent / "continuation-plan.json"
        if not prior_plan.exists():
            break
        starts.append(read_model(prior_plan, ContinuationPlan).first_ordinal)
    if consecutive_no_progress(tuple(reversed(starts)), ordinal) >= old.max_consecutive_no_progress:
        return False
    number = job.attempt_number + 1
    plan = old.model_copy(
        update={
            "first_ordinal": ordinal,
            "first_trial_id": job.prepared.matrices[job.index].trials[ordinal - 1].trial_id,
            "previous_selection": selected_path.relative_to(root).as_posix(),
            "output_relative_path": (
                "runs/t17-v2-live-20260904-02/"
                + outcome.stage.value
                + f"/continuation-{number - (3 if job.index == MODEL2_INDEX else 1):02d}"
            ),
            "snapshot_relative_path": snapshot.relative_to(root).as_posix(),
        }
    )
    target = plan_path(root, number, job.index)
    target.parent.mkdir(parents=True, exist_ok=True)
    write_checked_json(target, plan)
    return True


def interrupted_continuation(job: StageJob, reason: str) -> StageOutcome:
    """后处理故障也从真实新增日志计费，不能误读常规整轮尝试目录。"""
    root = job.prepared.setup.root
    plan = read_model(plan_path(root, job.attempt_number, job.index), ContinuationPlan)
    directory = inside(root, plan.output_relative_path)
    maximum = job.prepared.plan.stages[job.index].budget.max_total_usd
    proposal_path = directory / "budget-proposal.json"
    if proposal_path.exists():
        maximum = read_model(proposal_path, StageBudgetProposal).attempt_budget.max_total_usd
    result = StageOutcome(
        stage=job.prepared.matrices[job.index].stage,
        attempt_number=job.attempt_number,
        status="failed",
        reason=reason,
        raw_relative_path=(directory / "evidence").relative_to(root).as_posix(),
        usage=partial_usage(directory / "segment", maximum),
    )
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "stage-result.json"
    if target.exists():
        return read_model(target, StageOutcome)
    write_checked_json(target, result)
    return result
