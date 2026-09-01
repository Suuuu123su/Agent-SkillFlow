"""T16-B 模拟 Token 费用与达到上限后的部分保存。"""

from decimal import Decimal
from pathlib import Path
from typing import Final, assert_never

from skillflow.experiment.t16.budget import (
    BudgetConfig,
    BudgetExceededError,
    BudgetLedger,
    BudgetLimit,
    CallReservation,
)
from skillflow.experiment.t16.dry_run_errors import (
    FailureRehearsalError,
    FailureRehearsalReason,
)
from skillflow.experiment.t16.dry_run_failures import verify_budget_limit
from skillflow.experiment.t16.dry_run_io import DryRunResultStore, sha256_path
from skillflow.experiment.t16.dry_run_records import (
    CostChainProfile,
    DryRunTrialRecord,
    T16BDryRunConfig,
)
from skillflow.experiment.t16.dry_run_reports import (
    BudgetStopEvidence,
    CostCaseResult,
    CostMode,
    CostSimulationReport,
    FailureInjectionKind,
)
from skillflow.experiment.t16.provider import estimate_result_cost

ATTEMPT_COUNT: Final = 3
EXPECTED_SAVED_COUNT: Final = 2


def build_cost_simulation_report(
    config: T16BDryRunConfig,
    records: tuple[DryRunTrialRecord, ...],
    partial_path: Path,
) -> CostSimulationReport:
    """用冻结的假设价格计算六种费用并验证四类停止边界。"""
    cases: list[CostCaseResult] = []
    for profile in config.cost_profiles:
        cases.extend(
            (
                _cost_case(config, profile.profile, CostMode.NORMAL),
                _cost_case(config, profile.profile, CostMode.WORST_CASE),
            )
        )
    return CostSimulationReport(
        pricing=config.hypothetical_pricing,
        cases=tuple(cases),
        single_run_limit_blocked=verify_budget_limit(FailureInjectionKind.RUN_COST).blocked,
        total_limit_blocked=verify_budget_limit(FailureInjectionKind.TOTAL_COST).blocked,
        agent_step_limit_blocked=verify_budget_limit(FailureInjectionKind.AGENT_STEPS).blocked,
        retry_limit_blocked=verify_budget_limit(FailureInjectionKind.RETRY_LIMIT).blocked,
        partial_save=_rehearse_partial_save(records, partial_path),
    )


def _cost_case(
    config: T16BDryRunConfig,
    profile_name: CostChainProfile,
    mode: CostMode,
) -> CostCaseResult:
    definition = next(item for item in config.cost_profiles if item.profile is profile_name)
    match mode:
        case CostMode.NORMAL:
            usage = definition.normal_usage
            calls = definition.normal_api_calls
        case CostMode.WORST_CASE:
            usage = definition.worst_case_usage
            calls = definition.worst_case_api_calls
        case unreachable:
            assert_never(unreachable)
    return CostCaseResult(
        profile=profile_name,
        mode=mode,
        token_usage=usage,
        api_call_count=calls,
        estimated_cost_usd=estimate_result_cost(config.hypothetical_pricing, usage),
    )


def _rehearse_partial_save(
    records: tuple[DryRunTrialRecord, ...],
    path: Path,
) -> BudgetStopEvidence:
    if len(records) < ATTEMPT_COUNT:
        raise FailureRehearsalError(FailureRehearsalReason.TOO_FEW_RECORDS)
    store = DryRunResultStore(path)
    store.initialize()
    ledger = BudgetLedger(_partial_budget())
    saved_records: list[DryRunTrialRecord] = []
    for attempted, record in enumerate(records[:ATTEMPT_COUNT], start=1):
        try:
            ledger = ledger.begin_run().authorize_call(_reservation("0.01"))
        except BudgetExceededError as error:
            if error.limit is not BudgetLimit.TOTAL_COST:
                raise FailureRehearsalError(FailureRehearsalReason.PARTIAL_WRONG_LIMIT) from error
            saved_count = len(saved_records)
            return BudgetStopEvidence(
                limit=error.limit,
                attempted_result_count=attempted,
                saved_result_count=saved_count,
                existing_results_saved=saved_count == EXPECTED_SAVED_COUNT,
                saved_results_sha256=sha256_path(path),
            )
        store.append(record)
        saved_records.append(record)
    raise FailureRehearsalError(FailureRehearsalReason.TOTAL_NOT_STOPPED)


def _partial_budget() -> BudgetConfig:
    return BudgetConfig(
        allow_live=False,
        max_total_usd=Decimal("0.02"),
        max_cost_per_run_usd=Decimal("0.02"),
        max_agent_turns=1,
        max_output_tokens_per_turn=256,
        max_retries=1,
    )


def _reservation(cost: str) -> CallReservation:
    return CallReservation(estimated_cost_usd=Decimal(cost), max_output_tokens=1)
