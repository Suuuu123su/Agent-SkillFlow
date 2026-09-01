from decimal import Decimal

from tests.unit.experiment.t16.test_live_agent import (
    ScriptedClient,
    _config,
    _design,
    _final_turn,
    _function_turn,
    _tool_turn,
)

from skillflow.experiment.t16.budget import BudgetLedger
from skillflow.experiment.t16.live_agent import execute_live_trial
from skillflow.experiment.t16.live_metrics import build_live_metrics
from skillflow.experiment.t16.live_reanalysis import build_live_reanalysis
from skillflow.experiment.t16.live_records import LiveTrialRecord
from skillflow.experiment.t16.openai_responses import (
    OpenAIResponsesError,
    OpenAIResponsesErrorKind,
)
from skillflow.models.metrics import MetricStatus


def _record(condition_id: str, *, execute_alias: str | None = None) -> LiveTrialRecord:
    config = _config()
    script = (
        [_function_turn(execute_alias), _final_turn()]
        if execute_alias is not None
        else [_final_turn()]
    )
    return execute_live_trial(
        _design(condition_id),
        config,
        ScriptedClient(script),
        BudgetLedger(config.budget).begin_run(),
    ).record


def test_live_metrics_use_receipts_for_hiaa_and_keep_alr_rir_unavailable() -> None:
    records = (
        _record("c1-p00"),
        _record("c1-p01"),
        _record("c1-p10"),
        _record("c1-p11", execute_alias="operation-1"),
        _record("a1-claim", execute_alias="operation-1"),
        _record("a1-neutralized"),
    )

    report = build_live_metrics(records)

    assert report.hiaa.hiaa_run.value == 1.0
    assert report.hiaa.p11.executed_count == 1
    assert report.hiaa.p00.executed_count == 0
    assert report.uea.unauthorized_executed_count == 1
    assert report.alr.metric.status is MetricStatus.NOT_APPLICABLE
    assert report.rir_1.metric.status is MetricStatus.NOT_APPLICABLE
    assert report.rir_3.metric.status is MetricStatus.NOT_APPLICABLE
    assert report.alr.metric.value is None
    assert report.record_count == 6
    assert report.provenance_not_available_count == 6
    assert sum(item.rate.value or 0.0 for item in report.authorization_operational_rates) == 1.0
    assert records[4].result.estimated_cost_usd > Decimal(0)


def test_m2_missing_session_is_not_fabricated_as_zero() -> None:
    config = _config(max_retries=0)
    target = execute_live_trial(
        _design("m2-target"),
        config,
        ScriptedClient(
            [
                _tool_turn("read_asset", {"asset_id": "memory-payload"}, "asset"),
                _tool_turn(
                    "write_memory",
                    {"memory_key": "shared", "content": "memory-target!"},
                    "write",
                ),
                _final_turn(),
                _final_turn("refused"),
                OpenAIResponsesError(OpenAIResponsesErrorKind.TIMEOUT),
            ]
        ),
        BudgetLedger(config.budget).begin_run(),
    ).record
    records = (
        _record("c1-p00"),
        _record("c1-p01"),
        _record("c1-p10"),
        _record("c1-p11", execute_alias="operation-1"),
        target,
    )

    report = build_live_metrics(records)
    session_1 = next(
        item
        for item in report.m2_operational_rates
        if item.pair_role.value == "target" and item.session_index == 1
    )
    session_3 = next(
        item
        for item in report.m2_operational_rates
        if item.pair_role.value == "target" and item.session_index == 3
    )

    assert tuple(point.session_index for point in target.session_observations) == (1,)
    assert session_1.rate.denominator == 1
    assert session_1.rate.value == 0.0
    assert session_3.rate.status is MetricStatus.NOT_APPLICABLE


def test_hiaa_reports_invalid_and_completed_only_sensitivity() -> None:
    records = (
        execute_live_trial(
            _design("c1-p00"),
            _config(),
            ScriptedClient([_final_turn("refused")]),
            BudgetLedger(_config().budget).begin_run(),
        ).record,
        _record("c1-p01"),
        execute_live_trial(
            _design("c1-p10"),
            _config(),
            ScriptedClient([_final_turn("refused")]),
            BudgetLedger(_config().budget).begin_run(),
        ).record,
        _record("c1-p11", execute_alias="operation-1"),
    )

    report = build_live_reanalysis(records, "synthetic-trial-results.jsonl", "0" * 64)

    assert report.hiaa.p00.execution.observations.scheduled_count == 1
    assert report.hiaa.p00.execution.observations.valid_count == 0
    assert report.hiaa.p00.execution.observations.refusal_count == 1
    assert report.hiaa.p00.execution.valid_rate.status is MetricStatus.NOT_APPLICABLE
    assert report.hiaa.p01.execution.valid_rate.denominator == 1
    assert report.hiaa.p11.execution.valid_rate.value == 1.0
