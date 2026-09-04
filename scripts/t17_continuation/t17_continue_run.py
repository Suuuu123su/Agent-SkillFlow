"""从用户指定序号执行后缀，已有任务没有进入模型调用调度。"""

from pathlib import Path

from t17_continue_evidence import write_evidence
from t17_continue_models import (
    ContinuationAccounting,
    ContinuationPlan,
    SourceIndex,
    retained_sources,
    source_unit,
    terminal_path,
)

from skillflow.experiment.t17.minimal.artifacts import write_checked_json
from skillflow.experiment.t17.v2.api_models import V2LiveConfig
from skillflow.experiment.t17.v2.campaign import CampaignRuntime, budget_proposal
from skillflow.experiment.t17.v2.campaign_models import CampaignResult, StageOutcome
from skillflow.experiment.t17.v2.campaign_usage import journal_totals, progress
from skillflow.experiment.t17.v2.dataset_io import export_dataset
from skillflow.experiment.t17.v2.frozen import file_digest, inside
from skillflow.experiment.t17.v2.journal import read_journal
from skillflow.experiment.t17.v2.live_client import V2LiveClient
from skillflow.experiment.t17.v2.loading import read_model
from skillflow.experiment.t17.v2.run_models import CoreTerminal, PhaseContract, ReplayTerminal
from skillflow.experiment.t17.v2.stage import StageSetup, _prepare_phase, _write_terminal
from skillflow.experiment.t17.v2.stage_units import UnitScheduler
from skillflow.experiment.t17.v2.unit_execution import ExecutionContext
from skillflow.experiment.t17.v2.worker_models import StageJob

PLAN_RELATIVE = "docs/evidence/t17-v2-continuation-116.json"
MODEL2_INDEX = 3
FIRST_CONTINUATION_ATTEMPT = 4


def plan_path(root: Path, attempt_number: int, index: int = 3) -> Path:
    """返回用户首次指定断点或后续自动断点的已登记计划。"""
    if index == MODEL2_INDEX and attempt_number == FIRST_CONTINUATION_ATTEMPT:
        return root / PLAN_RELATIVE
    stage = "model2" if index == MODEL2_INDEX else "defense"
    return (
        root
        / "runs/t17-v2-live-20260904-02/continuation-plans"
        / f"{stage}-attempt-{attempt_number:03d}.json"
    )


def run_continuation(runtime: CampaignRuntime, job: StageJob) -> StageOutcome:  # noqa: PLR0915
    """一次流程内绑定原批准、前缀、后缀执行和费用，保持既有执行次序。"""
    prepared, root = runtime.prepared, runtime.prepared.setup.root
    plan = read_model(plan_path(root, job.attempt_number, job.index), ContinuationPlan)
    matrix, phase = prepared.matrices[job.index], prepared.phases[job.index]
    if job.index not in {3, 4}:
        raise ValueError("continuation_wrong_stage")
    snapshot = read_model(inside(root, plan.snapshot_relative_path), CampaignResult)
    if snapshot.stages != job.previous or snapshot.failed_attempts != job.failed:
        raise ValueError("continuation_accounting_snapshot_mismatch")
    source = inside(root, plan.source_raw)
    if read_model(source / "phase-contract.json", PhaseContract) != phase:
        raise ValueError("continuation_source_protocol_mismatch")
    sources = list(retained_sources(root, matrix, plan))
    cores = [read_model(terminal_path(root, s), CoreTerminal) for s in sources if s.kind == "core"]
    replays = [
        read_model(terminal_path(root, s), ReplayTerminal) for s in sources if s.kind == "replay"
    ]
    stage_dir = inside(root, plan.output_relative_path)
    proposal = budget_proposal(
        prepared,
        job.index,
        job.previous,
        failed=job.failed,
        attempt_number=job.attempt_number,
    )
    config = V2LiveConfig(
        provider=matrix.provider,
        budget=proposal.attempt_budget.model_copy(update={"allow_live": True}),
        matrix_sha256=phase.matrix_sha256,
        cost_plan_sha256=prepared.plan_sha256,
        approval_id=prepared.approval.approval_id,
        prompt_cache_mode="explicit" if matrix.provider.model_id == "gpt-5.6-luna" else "automatic",
        max_input_bytes=prepared.plan.stages[job.index].max_input_bytes_per_call,
    )
    client = V2LiveClient(config, runtime.secret, runtime.transport)
    segment = stage_dir / "segment"
    setup = StageSetup(
        root,
        segment,
        prepared.configuration,
        matrix,
        "live_reference",
        client,
        runtime.observer,
        phase,
    )
    checked_phase, accounting = _prepare_phase(setup)
    if accounting is None:
        raise ValueError("continuation_accounting_missing")
    stage_dir.mkdir(parents=True, exist_ok=False)
    write_checked_json(stage_dir / "continuation-plan.json", plan)
    write_checked_json(
        stage_dir / "retained-prefix.json", SourceIndex(plan=plan, units=tuple(sources))
    )
    write_checked_json(stage_dir / "budget-proposal.json", proposal)
    write_checked_json(stage_dir / "approved-live-config.json", config)
    segment.mkdir()
    write_checked_json(segment / "configuration.json", prepared.configuration)
    write_checked_json(segment / "matrix.json", matrix)
    write_checked_json(segment / "phase-contract.json", checked_phase)
    context = ExecutionContext(root, segment, prepared.configuration, matrix, checked_phase, client)
    scheduler = UnitScheduler(context, accounting)
    accounting.open_phase(segment, checked_phase)
    for ordinal, trial in enumerate(matrix.trials[plan.first_ordinal - 1 :], plan.first_ordinal):
        core, execution = scheduler.run_core(trial)
        cores.append(core)
        _write_terminal(segment, core)
        sources.append(source_unit(root, segment, ordinal, "core", trial.trial_id))
        if runtime.observer:
            runtime.observer(progress(phase, cores, replays))
        for alias, identifier in trial.replay_pair_ids.items():
            replay = scheduler.run_replay(trial, core, execution, alias)
            replays.append(replay)
            _write_terminal(segment, replay)
            sources.append(source_unit(root, segment, ordinal, "replay", identifier))
            if runtime.observer:
                runtime.observer(progress(phase, cores, replays))
    usage = journal_totals(read_journal(segment / "api-usage.jsonl"))
    selected = SourceIndex(plan=plan, units=tuple(sources))
    write_checked_json(stage_dir / "selected-sources.json", selected)
    loaded = write_evidence(setup, selected, stage_dir / "evidence")
    write_checked_json(
        stage_dir / "continuation-accounting.json",
        ContinuationAccounting(
            selected_result_usage=journal_totals(loaded.api_usage),
            new_execution_usage=usage,
        ),
    )
    passed = False
    dataset = stage_dir / "dataset"
    if loaded.result.gate.passed:
        passed = export_dataset(root, dataset, (loaded,)).all_provided_stages_passed
    outcome = StageOutcome(
        stage=matrix.stage,
        attempt_number=job.attempt_number,
        status="passed" if passed else "failed",
        reason=None if passed else "phase_gate_failed",
        gate=loaded.result.gate,
        raw_relative_path=loaded.raw_relative_path,
        raw_manifest=loaded.raw_manifest,
        dataset_relative_path=dataset.relative_to(root).as_posix() if passed else None,
        dataset_manifest=file_digest(dataset / "dataset-manifest.json") if passed else None,
        usage=usage,
    )
    write_checked_json(stage_dir / "stage-result.json", outcome)
    return outcome
