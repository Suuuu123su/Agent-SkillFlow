"""T16-C Session 成功与失败记录的统一构造。"""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum, unique

from skillflow.experiment.t16.live_records import LiveSessionRecord, LiveToolCallAudit
from skillflow.experiment.t16.provider import TokenUsage


@unique
class SessionOutcome(StrEnum):
    """Session 终态的封闭分类。"""

    COMPLETED = "completed"
    INCOMPLETE = "incomplete"
    NO_CALL = "no_call"
    REFUSAL = "refusal"
    SCHEMA_REJECTION = "schema_rejection"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    PROVIDER_ERROR = "provider_error"


@dataclass(frozen=True, slots=True)
class SessionTelemetry:
    """构造终态时共享的实际调用统计。"""

    usage: TokenUsage
    api_call_count: int
    latency_ms: int
    estimated_cost_usd: Decimal
    tool_calls: tuple[LiveToolCallAudit, ...]


@dataclass(frozen=True, slots=True)
class ProviderFailureDiagnostic:
    """仅包含白名单 Provider 错误字段，不包含响应正文。"""

    status_code: int | None = None
    error_type: str | None = None
    error_code: str | None = None
    error_param: str | None = None


def session_record(
    session_index: int,
    telemetry: SessionTelemetry,
    outcome: SessionOutcome,
    summary: str = "",
    provider_diagnostic: ProviderFailureDiagnostic | None = None,
) -> LiveSessionRecord:
    """把封闭终态机械映射为 Session 布尔字段。"""
    diagnostic = provider_diagnostic or ProviderFailureDiagnostic()
    return LiveSessionRecord(
        session_index=session_index,
        task_success=outcome is SessionOutcome.COMPLETED,
        no_call=outcome is SessionOutcome.NO_CALL,
        refusal=outcome is SessionOutcome.REFUSAL,
        schema_rejection=outcome is SessionOutcome.SCHEMA_REJECTION,
        timeout=outcome is SessionOutcome.TIMEOUT,
        rate_limit=outcome is SessionOutcome.RATE_LIMIT,
        provider_error=outcome is SessionOutcome.PROVIDER_ERROR,
        provider_status_code=diagnostic.status_code,
        provider_error_type=diagnostic.error_type,
        provider_error_code=diagnostic.error_code,
        provider_error_param=diagnostic.error_param,
        final_summary=summary,
        tool_calls=telemetry.tool_calls,
        token_usage=telemetry.usage,
        api_call_count=telemetry.api_call_count,
        latency_ms=telemetry.latency_ms,
        estimated_cost_usd=telemetry.estimated_cost_usd,
    )
