"""从逐响应日志重新计算用量，核对真实运行和阶段合同。"""

from decimal import Decimal

from skillflow.experiment.t16.provider import estimate_result_cost
from skillflow.experiment.t17.v2.api_models import ApiUsageEvent
from skillflow.experiment.t17.v2.canonical import model_digest
from skillflow.experiment.t17.v2.config_models import V2Matrix
from skillflow.experiment.t17.v2.phase_sources import phase_index
from skillflow.experiment.t17.v2.run_models import (
    CoreTerminal,
    ReplayTerminal,
    StageResult,
    UnitUsage,
)
from skillflow.experiment.t17.v2.usage_summary import summarize_usage


def journal_unit_usage(events: tuple[ApiUsageEvent, ...]) -> UnitUsage:
    """不读汇总值，逐条累加响应，包括格式失败和失败请求占用。"""
    return summarize_usage(events, reserved=events[-1].unit_reserved_usd if events else Decimal(0))


def validate_usage(
    result: StageResult, matrix: V2Matrix, events: tuple[ApiUsageEvent, ...]
) -> None:
    """只有响应全部绑定、记录与实际用量一致，才允许通过付费阶段。"""
    records: tuple[CoreTerminal | ReplayTerminal, ...] = (*result.cores, *result.replays)
    indexed = {r.identity.unit_id: r for r in records}
    phases = phase_index(result)
    for event in events:
        if (
            event.unit_id not in indexed
            or event.phase_contract_sha256 not in phases
            or event.matrix_sha256 != model_digest(matrix)
        ):
            raise ValueError("v2_usage_phase_unit_binding")
        if event.phase_contract_sha256 != indexed[event.unit_id].identity.phase_contract_sha256:
            raise ValueError("v2_usage_source_phase_binding")
        if event.event_type == "response":
            if event.usage is None or event.estimated_cost_usd != estimate_result_cost(
                matrix.provider.pricing, event.usage
            ):
                raise ValueError("v2_usage_cost_recompute")
            if event.model_revision != matrix.provider.model_revision:
                raise ValueError("v2_usage_model_revision_drift")
    for record in records:
        _validate_record(record, events, result.phase.domain == "live_reference")


def _validate_record(
    record: CoreTerminal | ReplayTerminal, events: tuple[ApiUsageEvent, ...], live: bool
) -> None:
    rows = tuple(e for e in events if e.unit_id == record.identity.unit_id)
    if not record.usage.complete:
        raise ValueError("v2_usage_incomplete")
    if record.usage != journal_unit_usage(rows):
        raise ValueError("v2_usage_terminal_totals_mismatch")
    if record.status != "completed":
        return
    decisions = {(d.run_id, d.session_id, d.step_id, d.call_id) for d in record.decisions}
    calls = {
        (e.call.run_id, e.call.session_id, e.call.step_id, e.call.call_id)
        for e in rows
        if e.event_type == "response" and e.call is not None
    }
    if live and calls != decisions:
        raise ValueError("v2_usage_call_decision_coverage")
    if rows:
        attempts = {e.attempt_index for e in rows if e.event_type == "attempt"}
        outcomes = {
            e.attempt_index
            for e in rows
            if e.event_type in {"response", "http_error", "transport_failure"}
        }
        settled = {e.attempt_index for e in rows if e.event_type == "settlement"}
        responses = {e.attempt_index for e in rows if e.event_type == "response"}
        if attempts != outcomes or responses != settled:
            raise ValueError("v2_usage_attempt_or_settlement_missing")
