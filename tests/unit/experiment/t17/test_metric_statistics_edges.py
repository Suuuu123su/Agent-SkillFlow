from decimal import Decimal
from pathlib import Path

import pytest

from skillflow.experiment.t16.provider import TokenUsage
from skillflow.experiment.t17 import phase_efficiency
from skillflow.experiment.t17.contracts import MeasurementStatus, RatioMeasurement
from skillflow.experiment.t17.live_attempt_models import (
    T17LiveStageSummary,
    T17LiveUnitRecord,
)
from skillflow.experiment.t17.live_reference_client import ReferenceLiveTelemetry
from skillflow.experiment.t17.metric_statistics import (
    ScheduledRatioContext,
    T17MetricNarrowingError,
    _narrow_measured_ratio,
    cluster_bootstrap_interval,
    percentile,
    scheduled_ratio,
    wilson_interval,
)
from skillflow.experiment.t17.phase_efficiency import (
    T17EfficiencyNarrowingError,
    aggregate_reference_telemetry,
    build_efficiency_summary,
    phase_source_hashes,
)


def _telemetry(
    calls: int,
    *,
    cost: str,
    latency: int,
) -> ReferenceLiveTelemetry:
    return ReferenceLiveTelemetry(
        api_call_count=calls,
        response_count=calls,
        agent_step_count=calls,
        retry_count=1,
        refusal_count=1,
        no_call_count=1,
        token_usage=TokenUsage(
            input_tokens=10,
            cached_input_tokens=2,
            output_tokens=3,
            reasoning_tokens=4,
        ),
        latency_ms=latency,
        estimated_cost_usd=Decimal(cost),
        conservative_reserved_usd=Decimal(cost),
    )


def test_scheduled_ratio_and_wilson_status_paths() -> None:
    context = ScheduledRatioContext(
        evidence_ids=("evidence-1",),
        incomplete_reason="partial",
        not_applicable_reason="none",
    )
    not_applicable = scheduled_ratio(0, 0, 0, context)
    incomplete = scheduled_ratio(1, 2, 3, context)
    measured = scheduled_ratio(2, 4, 4, context)

    assert not_applicable.status is MeasurementStatus.NOT_APPLICABLE
    assert incomplete.status is MeasurementStatus.INCOMPLETE
    assert measured.value == 0.5
    assert wilson_interval(incomplete).status is MeasurementStatus.INCOMPLETE
    interval = wilson_interval(measured)
    assert interval.status is MeasurementStatus.MEASURED
    assert interval.lower < interval.point < interval.upper
    assert str(T17MetricNarrowingError()) == "t17_measured_ratio_narrowing"


def test_bootstrap_and_percentile_paths() -> None:
    too_small = cluster_bootstrap_interval((0.5,), evidence_ids=("one",))
    interval = cluster_bootstrap_interval(
        (0.0, 0.5, 1.0),
        point=0.4,
        evidence_ids=("a", "b"),
    )

    assert too_small.status is MeasurementStatus.NOT_APPLICABLE
    assert interval.status is MeasurementStatus.MEASURED
    assert interval.point == 0.4
    assert interval.resamples == 10_000
    assert percentile((), 0.5) is None
    assert percentile((1.0,), 0.5) == 1.0
    assert percentile((0.0, 10.0), 0.25) == 2.5


def test_narrowing_rejects_malformed_measured_ratio() -> None:
    malformed = RatioMeasurement.model_construct(
        status=MeasurementStatus.MEASURED,
        numerator=None,
        denominator=None,
        value=None,
    )

    with pytest.raises(T17MetricNarrowingError):
        _narrow_measured_ratio(malformed)


def test_efficiency_summary_empty_and_observed_paths() -> None:
    total = _telemetry(3, cost="0.3", latency=30)
    summary = T17LiveStageSummary.model_construct(telemetry=total)
    empty = build_efficiency_summary((), summary)
    records = (
        T17LiveUnitRecord.model_construct(telemetry=_telemetry(1, cost="0.1", latency=10)),
        T17LiveUnitRecord.model_construct(telemetry=_telemetry(3, cost="0.3", latency=30)),
    )

    observed = build_efficiency_summary(records, summary)
    aggregated = aggregate_reference_telemetry(records)

    assert empty.unit_count == 0
    assert empty.api_calls_mean is None
    assert observed.unit_count == 2
    assert observed.api_calls_mean == 2
    assert observed.latency_ms_mean == 20
    assert observed.estimated_cost_usd_mean == Decimal("0.2")
    assert aggregated.api_call_count == 4
    assert aggregated.token_usage.input_tokens == 20
    assert aggregated.estimated_cost_usd == Decimal("0.4")


def test_efficiency_narrowing_and_source_hashes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = T17LiveUnitRecord.model_construct(telemetry=_telemetry(1, cost="0.1", latency=10))
    summary = T17LiveStageSummary.model_construct(telemetry=_telemetry(1, cost="0.1", latency=10))
    monkeypatch.setattr(phase_efficiency, "percentile", lambda *_args: None)

    with pytest.raises(T17EfficiencyNarrowingError):
        build_efficiency_summary((record,), summary)
    assert str(T17EfficiencyNarrowingError()) == ("t17_efficiency_percentile_narrowing")

    attempt = tmp_path / "attempt"
    attempt.mkdir()
    for name in (
        "live-summary.json",
        "trial-results.jsonl",
        "actual-usage-journal.jsonl",
        "preflight.json",
    ):
        (attempt / name).write_text(name, encoding="utf-8")
    matrix = tmp_path / "matrix.yaml"
    registry = tmp_path / "registry.yaml"
    matrix.write_text("matrix", encoding="utf-8")
    registry.write_text("registry", encoding="utf-8")

    hashes = phase_source_hashes(attempt, matrix, registry)

    assert set(hashes) == {
        "live_summary",
        "trial_results",
        "usage_journal",
        "preflight",
        "matrix",
        "scenario_registry",
    }
    assert all(len(value) == 64 for value in hashes.values())
