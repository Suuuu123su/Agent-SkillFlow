"""在现有保钥进程中执行两段 G；费用累计，网络故障从任务组断点恢复。"""

# ruff: noqa: T201

import json
from decimal import Decimal
from pathlib import Path

from t17_continue_models import SourceIndex, terminal_path
from t17_partial_resume import recover_partial_index
from t17_replacement_models import ReplacementJob, ReplacementPlan
from t17_replacement_worker import execute_replacement

from skillflow.experiment.t17.live_matrix import T17LiveStage
from skillflow.experiment.t17.minimal.artifacts import write_checked_json
from skillflow.experiment.t17.v2.campaign import partial_usage
from skillflow.experiment.t17.v2.campaign_models import StageOutcome
from skillflow.experiment.t17.v2.cost_models import BudgetApproval
from skillflow.experiment.t17.v2.frozen import file_digest, inside
from skillflow.experiment.t17.v2.journal import read_journal
from skillflow.experiment.t17.v2.key_keeper import MemoryKeyKeeper
from skillflow.experiment.t17.v2.loading import read_model
from skillflow.experiment.t17.v2.run_models import CoreTerminal, ReplayTerminal
from skillflow.experiment.t17.v2.session_models import CampaignReplacement
from skillflow.experiment.t17.v2.worker_models import WorkerMessage

ROOT = Path(__file__).resolve().parents[2]
RATE_LIMIT_STATUS = 429
SERVER_ERROR_MIN = 500
SERVER_ERROR_MAX = 599


def unfinished(root: Path, selection: SourceIndex) -> int | None:
    """按照固定序号寻找未闭合的任务组，不依赖模型成功与否。"""
    for source in sorted(selection.units, key=lambda s: (s.ordinal, s.kind)):
        model = CoreTerminal if source.kind == "core" else ReplayTerminal
        terminal = read_model(terminal_path(root, source), model)
        if terminal.status not in {"completed", "not_applicable"} or not terminal.usage.complete:
            return source.ordinal
    return None


def retryable(outcome: StageOutcome, events: tuple) -> bool:
    """仅接受已有账本证明的暂时性网络错误。"""
    gate = outcome.gate
    if (
        gate is None
        or not gate.infrastructure_invalid
        or gate.protocol_errors
        or gate.binding_failures
        or outcome.status == "postprocessing_failed"
    ):
        return False
    errors = [e for e in events if e.event_type in {"transport_failure", "http_error"}]
    if not errors:
        return False
    reason = errors[-1].reason or ""
    if reason.startswith("http_status_"):
        code = int(reason.removeprefix("http_status_"))
        return code == RATE_LIMIT_STATUS or SERVER_ERROR_MIN <= code <= SERVER_ERROR_MAX
    return reason in {"network_response_state_unknown", "timeout", "provider_error"}


def run_approved(  # noqa: C901, PLR0912, PLR0915
    keeper: MemoryKeyKeeper,
    replacement: CampaignReplacement,
) -> None:
    """在一个监督循环内共用原额度、批准及断点状态，不分裂保钥生命周期。"""
    plan = read_model(inside(ROOT, replacement.cost_plan), ReplacementPlan)
    approval = read_model(inside(ROOT, replacement.approval), BudgetApproval)
    if (
        replacement.protocol != plan.protocol
        or replacement.output != plan.output
        or approval.cost_plan_sha256 != file_digest(inside(ROOT, replacement.cost_plan)).sha256
        or approval.approved_max_total_usd != plan.allocated_usd
        or plan.allocated_usd > plan.remaining_approved_usd
    ):
        raise ValueError("replacement_approval_mismatch")
    if plan.prerequisite_outcomes:
        prerequisites = tuple(
            read_model(inside(ROOT, p), StageOutcome) for p in plan.prerequisite_outcomes
        )
        expected = (
            (T17LiveStage.MODEL1,)
            if plan.parallel_with_second_model
            else (T17LiveStage.MODEL2_CANARY, T17LiveStage.MODEL2)
        )
        if tuple(o.stage for o in prerequisites) != expected or any(
            o.status != "passed" or o.gate is None or not o.gate.passed for o in prerequisites
        ):
            raise ValueError("defense_requires_passed_prerequisite")
    output = inside(ROOT, plan.output)
    output.mkdir(parents=True, exist_ok=True)
    for stage_index, planned in enumerate(plan.stages):
        starts = []
        while True:
            all_outcomes = tuple(
                read_model(p, StageOutcome)
                for p in sorted(output.glob("*/attempt-*/stage-result.json"))
            )
            prior = tuple(o for o in all_outcomes if o.stage == planned.stage)
            if any(o.status == "passed" for o in prior):
                break
            number, ordinal, selection_path, source_raw = len(prior) + 1, 1, None, None
            if prior:
                last = output / planned.stage.value / f"attempt-{len(prior):02d}"
                approved_selection = (
                    plan.approved_prefix if stage_index == 0 else plan.approved_formal_prefix
                )
                approved_recovery = bool(approved_selection and len(prior) == 1)
                selection_path = (
                    approved_selection
                    if approved_recovery
                    else (last / "selected-sources.json").relative_to(ROOT).as_posix()
                )
                candidate = (
                    prior[-1]
                    if approved_recovery
                    else recover_partial_index(ROOT, last, prior[-1], plan)
                )
                if not inside(ROOT, selection_path).is_file():
                    print("[暂停] 上次未形成可续跑断点，保留密钥与记录。", flush=True)
                    return
                selected = read_model(inside(ROOT, selection_path), SourceIndex)
                raw = last / ("segment" if (last / "segment").exists() else "raw")
                if not approved_recovery and not retryable(
                    candidate, read_journal(raw / "api-usage.jsonl")
                ):
                    print("[暂停] 非网络类失败，不重新采样模型结果。", flush=True)
                    return
                ordinal = unfinished(ROOT, selected)
                if ordinal is None or starts[-3:] == [ordinal] * 3:
                    print("[暂停] 没有可续跑项或同一断点连续三次无进展。", flush=True)
                    return
                source_raw = raw.relative_to(ROOT).as_posix()
            spent = sum((o.usage.reserved_cost_usd for o in all_outcomes), Decimal(0))
            stage_spent = sum((o.usage.reserved_cost_usd for o in prior), Decimal(0))
            remaining = min(planned.budget.max_total_usd - stage_spent, plan.allocated_usd - spent)
            if remaining <= 0:
                print("[暂停] 已到阶段或总费用上限。", flush=True)
                return
            starts.append(ordinal)
            job = ReplacementJob(
                root=str(ROOT),
                plan=replacement.cost_plan,
                approval=replacement.approval,
                stage_index=stage_index,
                attempt_number=number,
                remaining_usd=remaining,
                first_ordinal=ordinal,
                previous_selection=selection_path,
                source_raw=source_raw,
                recorded_core_raw=plan.recorded_core_raw
                if ordinal == plan.recorded_core_ordinal
                else None,
                snapshot_relative_path=plan.source_snapshot,
            )
            print(
                f"[开始] {planned.stage.value}；从第 {ordinal} 条；剩余额度 ${remaining}",
                flush=True,
            )
            outcome = run_child(keeper, job, output)
            if outcome is None:
                return
            print(
                f"[阶段结果] {planned.stage.value}: {outcome.status}; "
                f"请求 {outcome.usage.api_calls}; 估算 ${outcome.usage.estimated_cost_usd}",
                flush=True,
            )
            if outcome.status == "passed":
                break
    if plan.model == "gpt-5.6-luna":
        print("[H 新增部分完成] 270/270；等待与 F 复用数据汇总，密钥继续保管。", flush=True)
    else:
        print(
            "[G 完成] DeepSeek 预检与正式阶段均通过；H 仍需 Luna，密钥继续留在本窗口内存。",
            flush=True,
        )


def run_child(keeper: MemoryKeyKeeper, job: ReplacementJob, output: Path) -> StageOutcome | None:
    """接收子进程实际进度与结果，退出时保存原新增费用。"""
    result = None
    error = None
    last_core = -1

    def receive(raw: bytes) -> None:
        nonlocal result, error, last_core
        message = WorkerMessage.model_validate_json(raw)
        if message.outcome is not None:
            result = message.outcome
        elif message.reason is not None:
            error = message.reason
        elif message.progress is not None:
            p = message.progress
            safe = {
                "stage": p.stage.value,
                "core": p.terminal_core,
                "core_total": p.scheduled_core,
                "replay": p.terminal_replay,
                "replay_total": p.scheduled_replay,
                "failed_units": p.failed_units,
                "model_failures": p.model_failures,
                "calls": p.usage.api_calls,
                "responses": p.usage.responses,
                "input_tokens": p.usage.input_tokens,
                "output_tokens": p.usage.output_tokens,
                "reasoning_tokens": p.usage.reasoning_tokens,
                "estimated_usd": str(p.usage.estimated_cost_usd),
                "reserved_usd": str(p.usage.reserved_cost_usd),
                "attempt": job.attempt_number,
            }
            # 可覆盖的进度显示不是原始证据；原始记录仍独占追加保存。
            (output / "latest-progress.json").write_text(json.dumps(safe), encoding="utf-8")
            if p.terminal_core != last_core:
                print(
                    f"{p.stage.value}: {p.terminal_core}/{p.scheduled_core}，"
                    f"重放 {p.terminal_replay}/{p.scheduled_replay}，请求 {p.usage.api_calls}，"
                    f"失败 {p.failed_units}，费用估算 ${p.usage.estimated_cost_usd}",
                    flush=True,
                )
                last_core = p.terminal_core

    exited = keeper.execute(job.model_dump_json().encode(), execute_replacement, receive)
    if result is None:
        plan = read_model(inside(ROOT, job.plan), ReplacementPlan)
        stage = plan.stages[job.stage_index].stage
        directory = output / stage.value / f"attempt-{job.attempt_number:02d}"
        directory.mkdir(parents=True, exist_ok=True)
        raw = directory / ("segment" if job.previous_selection else "raw")
        result = StageOutcome(
            stage=stage,
            attempt_number=job.attempt_number,
            status="failed",
            reason=error or exited.reason or "worker_no_outcome",
            raw_relative_path=raw.relative_to(ROOT).as_posix(),
            usage=partial_usage(raw, job.remaining_usd),
        )
        if not (directory / "stage-result.json").exists():
            write_checked_json(directory / "stage-result.json", result)
        print("[保钥暂停] 子进程退出：" + str(result.reason), flush=True)
    return result
