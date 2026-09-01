"""T16-B 本地故障注入与操作分类。"""

from dataclasses import dataclass
from decimal import Decimal
from typing import NoReturn, Protocol, assert_never

from pydantic import ValidationError

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
from skillflow.experiment.t16.dry_run_records import DryRunTrialRecord, T16BDryRunConfig
from skillflow.experiment.t16.dry_run_reports import (
    FailureInjectionKind,
    FailureInjectionReport,
    FailureInjectionResult,
    OperationalDisposition,
)
from skillflow.experiment.t16.provider import ProviderCallResult, ProviderRequest
from skillflow.experiment.t16.trial import TrialOutcome, TrialResult


class UnexpectedNetworkAccessError(RuntimeError):
    """测试保护层发现了任何网络访问尝试。"""


class NetworkProbe(Protocol):
    """可替换的意外网络访问探针。"""

    def attempt(self) -> None:
        """尝试触发受保护的网络边界。"""
        ...


class DeniedNetworkProbe:
    """生产演练默认使用的硬失败网络边界。"""

    def attempt(self) -> None:
        """在接触任何网络库前立即拒绝。"""
        raise UnexpectedNetworkAccessError


@dataclass(frozen=True, slots=True)
class _InjectedProviderError(RuntimeError):
    """纯本地 Fake Provider 的故障信号。"""

    kind: FailureInjectionKind


class _FaultingFakeProvider:
    """在调用边界内注入 timeout、限流或 Gateway 崩溃。"""

    def __init__(self, kind: FailureInjectionKind) -> None:
        """保存预注册故障类型。"""
        self._kind = kind

    def invoke(self, request: ProviderRequest, budget: BudgetLedger) -> NoReturn:
        """先走预算前置检查，再在本地产生指定失败。"""
        reservation = CallReservation(
            estimated_cost_usd=Decimal(0),
            max_output_tokens=request.max_output_tokens,
        )
        budget.authorize_call(reservation)
        raise _InjectedProviderError(self._kind)


def operational_disposition(result: TrialResult) -> OperationalDisposition:
    """在既有三分类之下区分 refusal、no-call 与其他 invalid。"""
    match result.outcome:
        case TrialOutcome.HARM:
            return OperationalDisposition.HARM
        case TrialOutcome.COMPLETED_WITHOUT_HARM:
            return OperationalDisposition.COMPLETED_WITHOUT_HARM
        case TrialOutcome.INVALID:
            if result.refusal and result.no_call:
                raise FailureRehearsalError(FailureRehearsalReason.CLASSIFICATION_OVERLAP)
            if result.refusal:
                return OperationalDisposition.REFUSAL
            if result.no_call:
                return OperationalDisposition.NO_CALL
            return OperationalDisposition.INVALID_OTHER
        case unreachable:
            assert_never(unreachable)


def verify_network_probe_is_blocked(probe: NetworkProbe) -> FailureInjectionResult:
    """确认网络探针只能以结构化硬失败结束。"""
    try:
        probe.attempt()
    except UnexpectedNetworkAccessError:
        return _passed(
            FailureInjectionKind.UNEXPECTED_NETWORK,
            "network_access_blocked",
            OperationalDisposition.INVALID_OTHER,
        )
    raise FailureRehearsalError(FailureRehearsalReason.NETWORK_NOT_BLOCKED)


def run_failure_injection_report(
    config: T16BDryRunConfig,
    records: tuple[DryRunTrialRecord, ...],
) -> FailureInjectionReport:
    """运行全部本地故障及 refusal/no-call 分类对照。"""
    safe = _find_record(records, TrialOutcome.COMPLETED_WITHOUT_HARM)
    harm = _find_record(records, TrialOutcome.HARM)
    results = (
        _provider_failure(config, FailureInjectionKind.PROVIDER_TIMEOUT),
        _provider_failure(config, FailureInjectionKind.RATE_LIMIT),
        _provider_failure(config, FailureInjectionKind.GATEWAY_CRASH),
        _missing_receipt(harm),
        _missing_token_info(),
        verify_budget_limit(FailureInjectionKind.RUN_COST),
        verify_budget_limit(FailureInjectionKind.TOTAL_COST),
        verify_budget_limit(FailureInjectionKind.AGENT_STEPS),
        verify_budget_limit(FailureInjectionKind.RETRY_LIMIT),
        verify_network_probe_is_blocked(DeniedNetworkProbe()),
        _classification_injection(safe, FailureInjectionKind.REFUSAL),
        _classification_injection(safe, FailureInjectionKind.NO_CALL),
    )
    dispositions = {item.disposition for item in results}
    required = {
        OperationalDisposition.REFUSAL,
        OperationalDisposition.NO_CALL,
        OperationalDisposition.INVALID_OTHER,
    }
    return FailureInjectionReport(
        results=results,
        all_blocked=all(item.blocked for item in results),
        classifications_are_distinct=required.issubset(dispositions),
    )


def verify_budget_limit(kind: FailureInjectionKind) -> FailureInjectionResult:
    """触发并复核一个费用、步数或重试边界。"""
    expected_limits = {
        FailureInjectionKind.RUN_COST: BudgetLimit.RUN_COST,
        FailureInjectionKind.TOTAL_COST: BudgetLimit.TOTAL_COST,
        FailureInjectionKind.AGENT_STEPS: BudgetLimit.AGENT_TURNS,
        FailureInjectionKind.RETRY_LIMIT: BudgetLimit.RETRIES,
    }
    expected = expected_limits.get(kind)
    if expected is None:
        raise FailureRehearsalError(
            FailureRehearsalReason.NOT_BUDGET_INJECTION,
            kind.value,
        )
    try:
        _trigger_budget_failure(kind)
    except BudgetExceededError as error:
        if error.limit is not expected:
            raise FailureRehearsalError(FailureRehearsalReason.BUDGET_WRONG_LIMIT) from error
        return _passed(kind, error.limit.value, OperationalDisposition.INVALID_OTHER)
    raise FailureRehearsalError(FailureRehearsalReason.BUDGET_NOT_STOPPED)


def _provider_failure(
    config: T16BDryRunConfig,
    kind: FailureInjectionKind,
) -> FailureInjectionResult:
    request = ProviderRequest(input_text="fake", estimated_input_tokens=1, max_output_tokens=1)
    try:
        _FaultingFakeProvider(kind).invoke(request, BudgetLedger(config.budget))
    except _InjectedProviderError as error:
        if error.kind is not kind:
            raise FailureRehearsalError(FailureRehearsalReason.PROVIDER_KIND_DRIFT) from error
        return _passed(kind, kind.value, OperationalDisposition.INVALID_OTHER)
    raise FailureRehearsalError(FailureRehearsalReason.PROVIDER_NOT_FAILED)


def _missing_receipt(record: DryRunTrialRecord) -> FailureInjectionResult:
    payload = record.result.model_dump(mode="python")
    payload["receipt_id"] = None
    try:
        TrialResult.model_validate(payload)
    except ValidationError:
        return _passed(
            FailureInjectionKind.MISSING_RECEIPT,
            "schema_rejection",
            OperationalDisposition.INVALID_OTHER,
        )
    raise FailureRehearsalError(FailureRehearsalReason.RECEIPT_ACCEPTED)


def _missing_token_info() -> FailureInjectionResult:
    try:
        ProviderCallResult.model_validate({"output_text": "fake", "latency_ms": 1})
    except ValidationError:
        return _passed(
            FailureInjectionKind.USAGE_METADATA_MISSING,
            "schema_rejection",
            OperationalDisposition.INVALID_OTHER,
        )
    raise FailureRehearsalError(FailureRehearsalReason.USAGE_ACCEPTED)


def _trigger_budget_failure(kind: FailureInjectionKind) -> None:
    if kind is FailureInjectionKind.RUN_COST:
        BudgetLedger(_budget("1.00", "0.01", turns=2)).authorize_call(_reservation("0.02"))
    elif kind is FailureInjectionKind.TOTAL_COST:
        ledger = BudgetLedger(_budget("0.02", "0.02", turns=2))
        ledger = ledger.authorize_call(_reservation("0.01")).begin_run()
        ledger.authorize_call(_reservation("0.02"))
    elif kind is FailureInjectionKind.AGENT_STEPS:
        ledger = BudgetLedger(_budget("1.00", "1.00", turns=1))
        ledger = ledger.authorize_call(_reservation("0"))
        ledger.authorize_call(_reservation("0"))
    elif kind is FailureInjectionKind.RETRY_LIMIT:
        ledger = BudgetLedger(_budget("1.00", "1.00", turns=2))
        ledger.record_retry().record_retry()
    else:
        raise FailureRehearsalError(
            FailureRehearsalReason.NOT_BUDGET_INJECTION,
            kind.value,
        )


def _classification_injection(
    record: DryRunTrialRecord,
    kind: FailureInjectionKind,
) -> FailureInjectionResult:
    payload = record.result.model_dump(mode="python")
    payload.update(
        {
            "task_success": False,
            "refusal": kind is FailureInjectionKind.REFUSAL,
            "no_call": kind is FailureInjectionKind.NO_CALL,
            "outcome": TrialOutcome.INVALID,
        }
    )
    result = TrialResult.model_validate(payload)
    return _passed(kind, kind.value, operational_disposition(result))


def _budget(total: str, per_run: str, *, turns: int) -> BudgetConfig:
    return BudgetConfig(
        allow_live=False,
        max_total_usd=Decimal(total),
        max_cost_per_run_usd=Decimal(per_run),
        max_agent_turns=turns,
        max_output_tokens_per_turn=256,
        max_retries=1,
    )


def _reservation(cost: str) -> CallReservation:
    return CallReservation(estimated_cost_usd=Decimal(cost), max_output_tokens=1)


def _find_record(
    records: tuple[DryRunTrialRecord, ...],
    outcome: TrialOutcome,
) -> DryRunTrialRecord:
    for record in records:
        if record.result.outcome is outcome:
            return record
    raise FailureRehearsalError(FailureRehearsalReason.SAMPLE_MISSING, outcome.value)


def _passed(
    kind: FailureInjectionKind,
    signal: str,
    disposition: OperationalDisposition,
) -> FailureInjectionResult:
    return FailureInjectionResult(
        kind=kind,
        blocked=True,
        observed_signal=signal,
        disposition=disposition,
    )
