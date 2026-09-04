"""已获批的阶段执行函数；正式入口由独立父进程保管密钥。"""

import getpass
import warnings
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import SecretStr

from skillflow.experiment.t16.openai_responses import ResponsesTransport
from skillflow.experiment.t17.minimal.artifacts import write_checked_json
from skillflow.experiment.t17.v2.api_models import V2LiveConfig
from skillflow.experiment.t17.v2.campaign_limits import SpendingHistory, remaining_budget
from skillflow.experiment.t17.v2.campaign_models import (
    CampaignResult,
    CredentialInputError,
    StageBudgetProposal,
    StageOutcome,
    StageProgress,
)
from skillflow.experiment.t17.v2.campaign_setup import PreparedCampaign, claim_campaign
from skillflow.experiment.t17.v2.campaign_usage import journal_totals
from skillflow.experiment.t17.v2.cost_history import historical_usage, projected_response_costs
from skillflow.experiment.t17.v2.dataset_io import export_dataset
from skillflow.experiment.t17.v2.frozen import file_digest
from skillflow.experiment.t17.v2.journal import read_journal
from skillflow.experiment.t17.v2.live_client import V2LiveClient
from skillflow.experiment.t17.v2.loading import load_stage, read_model
from skillflow.experiment.t17.v2.run_models import PhaseContract, StageResult, UnitUsage
from skillflow.experiment.t17.v2.stage import StageSetup, run_stage
from skillflow.experiment.t17.v2.static_protocol import verify_protocol


@dataclass(frozen=True, slots=True)
class CampaignRuntime:
    """密钥字段不进入表示、序列化文件或命令参数。"""

    prepared: PreparedCampaign
    secret: SecretStr = field(repr=False)
    transport: ResponsesTransport = field(repr=False)
    observer: Callable[[StageProgress], None] | None = None


def read_campaign_key() -> SecretStr:
    """隐藏输入不可用就停止；从不从参数、环境变量或文件读取密钥。"""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            raw = getpass.getpass("输入 API Key（仅保管进程内保存一次，不回显）：")
    except (getpass.GetPassWarning, EOFError, OSError) as error:
        raise CredentialInputError("v2_hidden_credential_input_unavailable") from error
    if not raw or not raw.strip():
        raise CredentialInputError("v2_empty_credential")
    return SecretStr(raw)


def run_campaign(runtime: CampaignRuntime) -> CampaignResult:
    """不重试阶段、不续填旧尝试；任一验收失败即停止后续阶段。"""
    prepared = runtime.prepared
    output = prepared.setup.output
    claim = claim_campaign(prepared)
    output.mkdir(parents=True, exist_ok=False)
    write_checked_json(output / "campaign-contract.json", claim)
    write_checked_json(output / "approved-cost-plan.json", prepared.plan)
    outcomes: list[StageOutcome] = []
    for index, _ in enumerate(prepared.matrices):
        outcome = run_one_stage(runtime, index, tuple(outcomes))
        outcomes.append(outcome)
        result = campaign_result(prepared, tuple(outcomes))
        write_checked_json(output / f"campaign-after-{index + 1:02d}.json", result)
        if outcome.status != "passed":
            break
    result = campaign_result(prepared, tuple(outcomes))
    write_checked_json(output / "campaign-result.json", result)
    return result


def run_one_stage(
    runtime: CampaignRuntime,
    index: int,
    previous: tuple[StageOutcome, ...],
    *,
    attempt_number: int = 1,
    failed: tuple[StageOutcome, ...] = (),
) -> StageOutcome:
    """先保存本阶段费用提案，再执行、重读和导出全部事实。"""
    prepared = runtime.prepared
    root, matrix = prepared.setup.root, prepared.matrices[index]
    config_now, matrices_now = verify_protocol(root, prepared.setup.protocol)
    if (
        config_now != prepared.configuration
        or matrices_now != prepared.matrices
        or file_digest(prepared.setup.protocol / "protocol-manifest.json")
        != prepared.plan.protocol_manifest
    ):
        raise ValueError("v2_approved_protocol_drift")
    approved_phase = read_model(
        prepared.setup.protocol / ("phase-" + matrix.stage.value + ".json"), PhaseContract
    )
    if approved_phase != prepared.phases[index]:
        raise ValueError("v2_prepared_phase_drift")
    stage_dir = prepared.setup.output / matrix.stage.value / f"attempt-{attempt_number:02d}"
    attempt = stage_dir / "raw"
    dataset = stage_dir / "dataset"
    proposal = budget_proposal(
        prepared, index, previous, failed=failed, attempt_number=attempt_number
    )
    stage_dir.mkdir(parents=True, exist_ok=False)
    write_checked_json(stage_dir / "budget-proposal.json", proposal)
    planned = prepared.plan.stages[index]
    config = V2LiveConfig(
        provider=matrix.provider,
        budget=proposal.attempt_budget.model_copy(update={"allow_live": True}),
        matrix_sha256=planned.matrix_sha256,
        cost_plan_sha256=prepared.plan_sha256,
        approval_id=prepared.approval.approval_id,
        prompt_cache_mode="explicit" if matrix.provider.model_id == "gpt-5.6-luna" else "automatic",
        max_input_bytes=planned.max_input_bytes_per_call,
    )
    write_checked_json(stage_dir / "approved-live-config.json", config)
    client = V2LiveClient(config, runtime.secret, runtime.transport)
    result: StageResult | None = None
    try:
        result = run_stage(
            StageSetup(
                root,
                attempt,
                prepared.configuration,
                matrix,
                "live_reference",
                client,
                runtime.observer,
                approved_phase,
            )
        )
        loaded = load_stage(root, attempt)
        manifest = export_dataset(root, dataset, (loaded,))
        status: Literal["passed", "failed"] = (
            "passed" if result.gate.passed and manifest.all_provided_stages_passed else "failed"
        )
        outcome = StageOutcome(
            stage=matrix.stage,
            attempt_number=attempt_number,
            status=status,
            reason=None if status == "passed" else "phase_gate_failed",
            gate=result.gate,
            raw_relative_path=_relative(root, attempt),
            raw_manifest=file_digest(attempt / "raw-manifest.json"),
            dataset_relative_path=_relative(root, dataset),
            dataset_manifest=file_digest(dataset / "dataset-manifest.json"),
            usage=journal_totals(loaded.api_usage),
        )
    except (Exception, KeyboardInterrupt) as error:  # noqa: BLE001 -- 保留已落盘的失败尝试并停止。
        outcome = StageOutcome(
            stage=matrix.stage,
            attempt_number=attempt_number,
            status="postprocessing_failed" if result is not None else "failed",
            reason=type(error).__name__,
            gate=None if result is None else result.gate,
            raw_relative_path=_relative(root, attempt),
            raw_manifest=file_digest(attempt / "raw-manifest.json")
            if (attempt / "raw-manifest.json").is_file()
            else None,
            usage=partial_usage(attempt, proposal.attempt_budget.max_total_usd),
        )
    write_checked_json(stage_dir / "stage-result.json", outcome)
    return outcome


def budget_proposal(
    prepared: PreparedCampaign,
    index: int,
    previous: tuple[StageOutcome, ...],
    *,
    failed: tuple[StageOutcome, ...] = (),
    attempt_number: int = 1,
) -> StageBudgetProposal:
    """只使用此前已结束的同模型响应更新估算，阶段和总上限绝不自动提高。"""
    if tuple(s.stage for s in previous) != tuple(m.stage for m in prepared.matrices[:index]) or any(
        s.status != "passed" or s.gate is None or not s.gate.passed for s in previous
    ):
        raise ValueError("v2_previous_stage_gate_not_passed")
    planned = prepared.plan.stages[index]
    history = SpendingHistory(previous, failed)
    attempt_budget = remaining_budget(
        planned.stage, planned.budget, prepared.approval.approved_max_total_usd, history
    )
    estimated, reserved = history.estimated_usd, history.reserved_usd
    remaining = prepared.approval.approved_max_total_usd - reserved
    root = prepared.setup.root
    samples = tuple(
        event.usage
        for stage in previous
        for event in read_journal(root / stage.raw_relative_path / "api-usage.jsonl")
        if event.event_type == "response"
        and event.model_revision == prepared.matrices[index].provider.model_revision
        and event.usage is not None
    )
    source: Literal["prior_same_model_responses", "historical_planning_only"] = (
        "prior_same_model_responses" if samples else "historical_planning_only"
    )
    if not samples:
        _, samples = historical_usage(root, root / prepared.plan.historical.source_path)
    mean, p95 = projected_response_costs(planned.rates, samples)
    return StageBudgetProposal(
        stage_cost=planned,
        attempt_number=attempt_number,
        attempt_budget=attempt_budget,
        failed_attempt_count=len(failed),
        cost_plan_sha256=prepared.plan_sha256,
        approval_id=prepared.approval.approval_id,
        approved_total_usd=prepared.approval.approved_max_total_usd,
        previous_estimated_usd=estimated,
        previous_reserved_usd=reserved,
        remaining_approved_usd=remaining,
        projected_from=source,
        observed_responses=len(samples),
        expected_estimated_usd=mean * planned.no_failure_api_calls,
        p95_projected_usd=p95 * planned.no_failure_api_calls,
    )


def campaign_result(
    prepared: PreparedCampaign,
    outcomes: tuple[StageOutcome, ...],
    *,
    failed: tuple[StageOutcome, ...] = (),
) -> CampaignResult:
    """保守余额扣除失败预留，不把未知费用回填为零。"""
    history = SpendingHistory(outcomes, failed)
    estimated, reserved = history.estimated_usd, history.reserved_usd
    return CampaignResult(
        cost_plan_sha256=prepared.plan_sha256,
        approval_id=prepared.approval.approval_id,
        approved_total_usd=prepared.approval.approved_max_total_usd,
        estimated_cost_usd=estimated,
        reserved_cost_usd=reserved,
        remaining_approved_usd=max(Decimal(0), prepared.approval.approved_max_total_usd - reserved),
        stages=outcomes,
        failed_attempts=failed,
        usage_complete=all(s.usage.complete for s in history.all_outcomes),
        all_stages_finished=len(outcomes) == len(prepared.matrices)
        and all(s.status == "passed" for s in outcomes),
    )


def _relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def partial_usage(attempt: Path, maximum: Decimal) -> UnitUsage:
    """日志不可读时占用本次全部额度，禁止以未知零费用重新开跑。"""
    try:
        path = attempt / "api-usage.jsonl"
        return journal_totals(read_journal(path)) if path.is_file() else UnitUsage()
    except (ValueError, OSError):
        return UnitUsage(
            complete=False, missing_reason="journal_unreadable", reserved_cost_usd=maximum
        )
