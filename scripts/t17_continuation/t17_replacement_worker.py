"""替换模型的独立工作进程，复用原任务、重放、证据和指标计算。"""

from contextlib import suppress
from decimal import Decimal
from multiprocessing.connection import Connection
from pathlib import Path

from pydantic import SecretStr
from t17_continue_evidence import write_evidence
from t17_continue_models import (
    ContinuationPlan,
    SourceIndex,
    retained_sources,
    source_unit,
    terminal_path,
)
from t17_recorded_core import restore_recorded_core
from t17_replacement_models import ReplacementJob, ReplacementPlan

from skillflow.experiment.t17.live_matrix import T17LiveStage
from skillflow.experiment.t17.minimal.artifacts import write_checked_json
from skillflow.experiment.t17.v2.analysis_context import AnalysisGroup
from skillflow.experiment.t17.v2.api_models import ApiUsageEvent, V2LiveConfig
from skillflow.experiment.t17.v2.campaign import partial_usage
from skillflow.experiment.t17.v2.campaign_models import (
    StageBudgetProposal,
    StageOutcome,
    StageProgress,
)
from skillflow.experiment.t17.v2.campaign_usage import progress
from skillflow.experiment.t17.v2.config_models import V2Configuration, V2Matrix
from skillflow.experiment.t17.v2.cost_history import projected_response_costs
from skillflow.experiment.t17.v2.cost_models import BudgetApproval
from skillflow.experiment.t17.v2.dataset_io import export_dataset
from skillflow.experiment.t17.v2.frozen import file_digest, inside
from skillflow.experiment.t17.v2.journal import read_journal
from skillflow.experiment.t17.v2.live_client import V2LiveClient
from skillflow.experiment.t17.v2.loaded_models import LoadedStage
from skillflow.experiment.t17.v2.loading import load_stage, read_model
from skillflow.experiment.t17.v2.network import managed_transport
from skillflow.experiment.t17.v2.phase_gate import build_gate
from skillflow.experiment.t17.v2.phase_sources import phase_index
from skillflow.experiment.t17.v2.run_models import (
    CoreTerminal,
    PhaseContract,
    ReplayTerminal,
    StageResult,
)
from skillflow.experiment.t17.v2.stage import (
    StageRawManifest,
    StageSetup,
    _prepare_phase,
    _write_terminal,
    run_stage,
)
from skillflow.experiment.t17.v2.stage_units import UnitScheduler
from skillflow.experiment.t17.v2.unit_execution import ExecutionContext
from skillflow.experiment.t17.v2.worker_models import WorkerMessage


def execute_replacement(channel: Connection) -> None:
    """只从匿名管道接收密钥和已批准任务，不把密钥写入结果。"""
    try:
        secret = SecretStr(channel.recv_bytes(8192).decode("utf-8"))
        job = ReplacementJob.model_validate_json(channel.recv_bytes(64 * 1024 * 1024))
        outcome = run_job(job, secret, channel)
        channel.send_bytes(
            WorkerMessage(kind="outcome", outcome=outcome).model_dump_json().encode()
        )
    except BaseException as error:  # noqa: BLE001 -- 不传播异常正文或凭据。
        with suppress(OSError):
            channel.send_bytes(
                WorkerMessage(kind="error", reason=type(error).__name__).model_dump_json().encode()
            )
    finally:
        channel.close()


def run_job(job: ReplacementJob, secret: SecretStr, channel: Connection) -> StageOutcome:
    """执行一次受预算限制的任务或后缀，并保存真实终态。"""
    root = Path(job.root).resolve()
    plan = read_model(inside(root, job.plan), ReplacementPlan)
    approval = read_model(inside(root, job.approval), BudgetApproval)
    planned = plan.stages[job.stage_index]
    if (
        approval.cost_plan_sha256 != file_digest(inside(root, job.plan)).sha256
        or approval.approved_max_total_usd != plan.allocated_usd
        or job.remaining_usd > planned.budget.max_total_usd
        or plan.allocated_usd > plan.remaining_approved_usd
    ):
        raise ValueError("replacement_budget_binding")
    protocol = inside(root, plan.protocol)
    config = read_model(protocol / "preregistration.json", V2Configuration)
    matrix = read_model(protocol / f"matrix-{planned.stage.value}.json", V2Matrix)
    phase = read_model(protocol / f"phase-{planned.stage.value}.json", PhaseContract)
    expected_provider = config.model1 if planned.stage is T17LiveStage.DEFENSE else config.model2
    if (
        matrix.provider.model_id != plan.model
        or matrix.provider != expected_provider
        or phase.matrix_sha256 != planned.matrix_sha256
    ):
        raise ValueError("replacement_model_binding")
    stage_dir = (
        inside(root, plan.output) / planned.stage.value / f"attempt-{job.attempt_number:02d}"
    )
    stage_dir.mkdir(parents=True, exist_ok=False)
    budget = planned.budget.model_copy(
        update={"allow_live": True, "max_total_usd": job.remaining_usd}
    )
    live = V2LiveConfig(
        provider=matrix.provider,
        budget=budget,
        endpoint=plan.endpoint,
        matrix_sha256=phase.matrix_sha256,
        cost_plan_sha256=approval.cost_plan_sha256,
        approval_id=approval.approval_id,
        prompt_cache_mode="automatic",
    )
    write_checked_json(stage_dir / "approved-live-config.json", live)
    save_proposal(root, stage_dir, plan, job, approval, live)
    write_checked_json(stage_dir / "execution-command.json", job.model_copy(update={"root": "."}))
    raw = stage_dir / ("raw" if job.previous_selection is None else "segment")

    def observe(value: StageProgress) -> None:
        channel.send_bytes(
            WorkerMessage(kind="progress", progress=value).model_dump_json().encode()
        )

    loaded = None
    with managed_transport(plan.endpoint) as transport:
        client = V2LiveClient(live, secret, transport)
        setup = StageSetup(root, raw, config, matrix, "live_reference", client, observe, phase)
        try:
            if job.previous_selection is None:
                result = run_stage(setup)
                selection = initial_selection(job, setup, stage_dir)
                if result.gate.passed:
                    loaded = load_stage(root, raw)
                else:
                    manifest = read_model(raw / "raw-manifest.json", StageRawManifest)
                    loaded = LoadedStage(
                        configuration=config,
                        matrix=matrix,
                        result=result,
                        raw_relative_path=raw.relative_to(root).as_posix(),
                        raw_manifest=file_digest(raw / "raw-manifest.json"),
                        raw_files=manifest.files,
                        api_usage=read_journal(raw / "api-usage.jsonl"),
                    )
            else:
                selection = continue_suffix(job, setup, stage_dir)
                loaded = write_evidence(setup, selection, stage_dir / "evidence")
            write_checked_json(stage_dir / "selected-sources.json", selection)
            dataset = stage_dir / "dataset"
            passed = loaded.result.gate.passed
            if passed:
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
                usage=partial_usage(raw, job.remaining_usd),
            )
        except (Exception, KeyboardInterrupt) as error:  # noqa: BLE001
            outcome = StageOutcome(
                stage=matrix.stage,
                attempt_number=job.attempt_number,
                status="postprocessing_failed" if loaded is not None else "failed",
                reason=type(error).__name__,
                gate=loaded.result.gate if loaded else None,
                raw_relative_path=raw.relative_to(root).as_posix(),
                usage=partial_usage(raw, job.remaining_usd),
            )
    write_checked_json(stage_dir / "stage-result.json", outcome)
    return outcome


def save_proposal(  # noqa: PLR0913, PLR0917
    root: Path,
    directory: Path,
    plan: ReplacementPlan,
    job: ReplacementJob,
    approval: BudgetApproval,
    live: V2LiveConfig,
) -> None:
    """正式阶段使用已返回的 DeepSeek 预检用量更新预测，不提高费用门。"""
    planned = plan.stages[job.stage_index]
    previous = tuple(
        read_model(p, StageOutcome)
        for p in inside(root, plan.output).glob("*/attempt-*/stage-result.json")
    )
    samples = tuple(
        event.usage
        for outcome in previous
        if outcome.status == "passed"
        for line in (inside(root, outcome.raw_relative_path) / "api-usage.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        for event in (ApiUsageEvent.model_validate_json(line),)
        if event.event_type == "response"
        and event.usage is not None
        and event.model_revision == plan.model
    )
    if not samples and plan.usage_reference:
        samples = tuple(
            e.usage
            for e in read_journal(inside(root, plan.usage_reference))
            if e.event_type == "response" and e.usage is not None and e.model_revision == plan.model
        )
    mean, p95 = projected_response_costs(planned.rates, samples) if samples else (None, None)
    reserved = sum((o.usage.reserved_cost_usd for o in previous), Decimal(0))
    write_checked_json(
        directory / "budget-proposal.json",
        StageBudgetProposal(
            stage_cost=planned,
            attempt_number=job.attempt_number,
            attempt_budget=live.budget.model_copy(update={"allow_live": False}),
            failed_attempt_count=sum(o.status != "passed" for o in previous),
            cost_plan_sha256=approval.cost_plan_sha256,
            approval_id=approval.approval_id,
            approved_total_usd=plan.allocated_usd,
            previous_estimated_usd=sum((o.usage.estimated_cost_usd for o in previous), Decimal(0)),
            previous_reserved_usd=reserved,
            remaining_approved_usd=plan.allocated_usd - reserved,
            projected_from="prior_same_model_responses" if samples else "historical_planning_only",
            observed_responses=len(samples),
            expected_estimated_usd=mean * planned.no_failure_api_calls
            if mean is not None
            else planned.expected_estimated_usd,
            p95_projected_usd=p95 * planned.no_failure_api_calls
            if p95 is not None
            else planned.historical_p95_projected_usd,
        ),
    )


def continuation_plan(job: ReplacementJob, setup: StageSetup, stage_dir: Path) -> ContinuationPlan:
    """保存当前尝试的固定断点及原始来源。"""
    root = setup.project_root
    return ContinuationPlan(
        source_raw=job.source_raw or setup.output.relative_to(root).as_posix(),
        output_relative_path=stage_dir.relative_to(root).as_posix(),
        snapshot_relative_path=job.snapshot_relative_path,
        first_ordinal=job.first_ordinal,
        first_trial_id=setup.matrix.trials[job.first_ordinal - 1].trial_id,
        previous_selection=job.previous_selection,
        user_instruction=(
            "第二模型 DeepSeek；用户允许完整用量超限空响应按模型失败记录，"
            "第 13 个任务使用原响应恢复，不重采；网络中断从未完成任务组续跑。"
        ),
    )


def initial_selection(job: ReplacementJob, setup: StageSetup, directory: Path) -> SourceIndex:
    """为第一次尝试的全部调度单元登记实际终态。"""
    units = []
    for ordinal, trial in enumerate(setup.matrix.trials, 1):
        units.append(source_unit(setup.project_root, setup.output, ordinal, "core", trial.trial_id))
        units.extend(
            source_unit(setup.project_root, setup.output, ordinal, "replay", identifier)
            for identifier in trial.replay_pair_ids.values()
        )
    return SourceIndex(plan=continuation_plan(job, setup, directory), units=tuple(units))


def continue_suffix(job: ReplacementJob, setup: StageSetup, directory: Path) -> SourceIndex:
    """保留已完成前缀，只执行未完成后缀与获准的原响应恢复。"""
    root, phase = setup.project_root, setup.approved_phase
    plan = continuation_plan(job, setup, directory)
    source_phase = read_model(inside(root, plan.source_raw) / "phase-contract.json", PhaseContract)
    sources = list(retained_sources(root, setup.matrix, plan))
    cores = [read_model(terminal_path(root, s), CoreTerminal) for s in sources if s.kind == "core"]
    replays = [
        read_model(terminal_path(root, s), ReplayTerminal) for s in sources if s.kind == "replay"
    ]
    if source_phase != phase:
        partial = build_gate(
            phase,
            setup.matrix,
            AnalysisGroup(setup.configuration, tuple(cores), tuple(replays)),
            source_phases=(source_phase,),
        )
        phase_index(
            StageResult(
                phase=phase,
                source_phases=(source_phase,),
                cores=tuple(cores),
                replays=tuple(replays),
                gate=partial,
            )
        )
    checked, accounting = _prepare_phase(setup)
    if accounting is None:
        raise ValueError("replacement_accounting_missing")
    write_checked_json(directory / "continuation-plan.json", plan)
    raw = setup.output
    raw.mkdir(exist_ok=False)
    write_checked_json(raw / "configuration.json", setup.configuration)
    write_checked_json(raw / "matrix.json", setup.matrix)
    write_checked_json(raw / "phase-contract.json", checked)
    context = ExecutionContext(root, raw, setup.configuration, setup.matrix, checked, setup.client)
    scheduler = UnitScheduler(context, accounting)
    accounting.open_phase(raw, checked)
    for ordinal, trial in enumerate(
        setup.matrix.trials[plan.first_ordinal - 1 :], plan.first_ordinal
    ):
        if job.recorded_core_raw and ordinal == plan.first_ordinal:
            recovered_raw = directory / "recovered-core"
            execution = restore_recorded_core(setup, trial, recovered_raw, job.recorded_core_raw)
            core = execution.terminal
            sources.append(source_unit(root, recovered_raw, ordinal, "core", trial.trial_id))
        else:
            core, execution = scheduler.run_core(trial)
            _write_terminal(raw, core)
            sources.append(source_unit(root, raw, ordinal, "core", trial.trial_id))
        cores.append(core)
        if setup.observer:
            setup.observer(progress(checked, cores, replays))
        for alias, identifier in trial.replay_pair_ids.items():
            replay = scheduler.run_replay(trial, core, execution, alias)
            replays.append(replay)
            _write_terminal(raw, replay)
            sources.append(source_unit(root, raw, ordinal, "replay", identifier))
            if setup.observer:
                setup.observer(progress(checked, cores, replays))
    return SourceIndex(plan=plan, units=tuple(sources))
