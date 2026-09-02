from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from skillflow.experiment.t16.provider import TokenUsage
from skillflow.experiment.t17 import defense_report as module
from skillflow.experiment.t17.contracts import MeasurementStatus, RatioMeasurement
from skillflow.experiment.t17.defense_models import (
    T17DefenseModeMetrics,
    T17SecurityGain,
)
from skillflow.experiment.t17.defense_report import (
    T17DefenseReportError,
    T17DefenseReportRequest,
    _build_mode,
    _ModeBuildRequest,
    _validated_phase,
    build_defense_report,
    write_defense_report,
)
from skillflow.experiment.t17.live_attempt_models import T17LiveUnitKind
from skillflow.experiment.t17.live_reference_client import ReferenceLiveTelemetry
from skillflow.experiment.t17.metric_models import T17PhaseMetricsReport
from skillflow.models.enums import EnforcementMode


def _ratio(value: float) -> RatioMeasurement:
    return RatioMeasurement(
        status=MeasurementStatus.MEASURED,
        numerator=round(value * 100),
        denominator=100,
        scheduled_denominator=100,
        value=value,
    )


def _telemetry(cost: str, latency: int, calls: int) -> ReferenceLiveTelemetry:
    return ReferenceLiveTelemetry(
        api_call_count=calls,
        response_count=calls,
        agent_step_count=calls,
        retry_count=0,
        refusal_count=0,
        no_call_count=0,
        token_usage=TokenUsage(
            input_tokens=10,
            cached_input_tokens=0,
            output_tokens=3,
            reasoning_tokens=2,
        ),
        latency_ms=latency,
        estimated_cost_usd=Decimal(cost),
        conservative_reserved_usd=Decimal(cost),
    )


def _mode(mode: EnforcementMode) -> T17DefenseModeMetrics:
    value = 0.8 if mode is EnforcementMode.MONITOR else 0.2
    return T17DefenseModeMetrics.model_construct(
        mode=mode,
        scheduled_core_trials=315,
        scheduled_replay_pairs=270,
        task_success_rate=_ratio(value),
        safe_task_success_rate=_ratio(value),
        telemetry=_telemetry(
            "0.8" if mode is EnforcementMode.MONITOR else "0.2",
            80 if mode is EnforcementMode.MONITOR else 20,
            8 if mode is EnforcementMode.MONITOR else 2,
        ),
    )


def _phase(complete: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        required_metrics_complete=complete,
        evidence_domain=SimpleNamespace(model_revision="model"),
    )


def _raw(core: int, replay: int) -> SimpleNamespace:
    records = tuple(SimpleNamespace(unit_kind=T17LiveUnitKind.CORE) for _ in range(core)) + tuple(
        SimpleNamespace(unit_kind=T17LiveUnitKind.REPLAY) for _ in range(replay)
    )
    return SimpleNamespace(records=records, runs_by_trial={}, replays_by_unit={})


def _request(tmp_path: Path) -> T17DefenseReportRequest:
    model1 = tmp_path / "model1"
    defense = tmp_path / "defense"
    model1.mkdir()
    defense.mkdir()
    (model1 / "phase-metrics.json").write_text("{}\n", encoding="utf-8")
    (defense / "phase-metrics.json").write_text("{}\n", encoding="utf-8")
    paths = [tmp_path / name for name in ("m1.yaml", "d.yaml", "r.yaml", "b.yaml")]
    for path in paths:
        path.write_text("x\n", encoding="utf-8")
    return T17DefenseReportRequest(
        model1,
        defense,
        paths[0],
        paths[1],
        paths[2],
        paths[3],
        tmp_path / "defense-report.json",
    )


def _patch_complete_sources(
    monkeypatch: pytest.MonkeyPatch,
    *,
    core_per_source: int = 315,
    replay_per_source: int = 270,
) -> None:
    monkeypatch.setattr(
        module, "load_scenario_measurement_registry", lambda _path: SimpleNamespace(scenarios=())
    )
    monkeypatch.setattr(
        module, "validate_yaml_document", lambda *_args: SimpleNamespace(variants=())
    )
    matrices = iter((SimpleNamespace(trials=()), SimpleNamespace(trials=())))
    monkeypatch.setattr(module, "load_live_matrix", lambda _path: next(matrices))
    monkeypatch.setattr(module, "_validated_phase", lambda *_args: _phase())
    raws = iter(
        (
            _raw(core_per_source, replay_per_source),
            _raw(core_per_source, replay_per_source),
        )
    )
    monkeypatch.setattr(module, "load_phase_artifacts", lambda _path: next(raws))
    monkeypatch.setattr(module, "_build_mode", lambda source: _mode(source.mode))
    gain = T17SecurityGain(
        metric="risk",
        status=MeasurementStatus.MEASURED,
        monitor_value=0.8,
        enforce_value=0.2,
        security_gain=0.6,
    )
    monkeypatch.setattr(module, "_security_gains", lambda *_args: (gain,))
    monkeypatch.setattr(module, "_over_defense_rate", lambda *_args: _ratio(0.1))


def test_build_and_write_defense_report_complete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_complete_sources(monkeypatch)
    request = _request(tmp_path)

    report = write_defense_report(request)

    assert report.complete is True
    assert report.combined_core_trials == 630
    assert report.utility_loss == pytest.approx(0.6)
    assert report.safe_tsr_delta == pytest.approx(0.6)
    assert report.estimated_cost_delta_enforce_minus_monitor_usd == Decimal("-0.6")
    assert report.latency_delta_enforce_minus_monitor_ms == -60
    assert report.token_delta_enforce_minus_monitor == 0
    assert report.api_call_delta_enforce_minus_monitor == -6
    assert report.agent_step_delta_enforce_minus_monitor == -6
    assert request.output_path.is_file()


def test_defense_report_rejects_incomplete_phase(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _request(tmp_path)
    monkeypatch.setattr(
        module, "load_scenario_measurement_registry", lambda _path: SimpleNamespace(scenarios=())
    )
    monkeypatch.setattr(
        module, "validate_yaml_document", lambda *_args: SimpleNamespace(variants=())
    )
    monkeypatch.setattr(module, "load_live_matrix", lambda _path: SimpleNamespace(trials=()))
    monkeypatch.setattr(module, "_validated_phase", lambda *_args: _phase(complete=False))

    with pytest.raises(T17DefenseReportError, match="source_phase_incomplete"):
        build_defense_report(request)


def test_defense_report_rejects_wrong_combined_counts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_complete_sources(monkeypatch, core_per_source=1, replay_per_source=1)

    with pytest.raises(T17DefenseReportError, match="combined_count_invalid"):
        build_defense_report(_request(tmp_path))


def test_validated_phase_detects_stored_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempt = tmp_path / "attempt"
    attempt.mkdir()
    (attempt / "phase-metrics.json").write_text("{}\n", encoding="utf-8")
    rebuilt = object()
    monkeypatch.setattr(module, "build_phase_metrics_report", lambda _request: rebuilt)
    monkeypatch.setattr(
        T17PhaseMetricsReport,
        "model_validate_json",
        classmethod(lambda _cls, _raw: rebuilt),
    )

    assert (
        _validated_phase(
            attempt,
            tmp_path / "m.yaml",
            tmp_path / "r.yaml",
            tmp_path / "b.yaml",
        )
        is rebuilt
    )

    monkeypatch.setattr(
        T17PhaseMetricsReport,
        "model_validate_json",
        classmethod(lambda _cls, _raw: object()),
    )
    with pytest.raises(T17DefenseReportError, match="phase_rebuild_mismatch"):
        _validated_phase(
            attempt,
            tmp_path / "m.yaml",
            tmp_path / "r.yaml",
            tmp_path / "b.yaml",
        )


def test_build_mode_routes_static_id_sets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = object()
    captured: list[object] = []
    monkeypatch.setattr(
        module,
        "build_defense_mode_metrics",
        lambda value: captured.append(value) or result,
    )
    source = _ModeBuildRequest(
        EnforcementMode.MONITOR,
        (),
        (),
        {},
        {},
        {},
        SimpleNamespace(
            hiaa_designs=(SimpleNamespace(harm_selector=object()),),
        ),
    )

    assert _build_mode(source) is result
    assert captured[0].mode is EnforcementMode.MONITOR
    assert captured[0].scheduled_core_ids == frozenset()
    assert captured[0].scheduled_replay_ids == frozenset()
