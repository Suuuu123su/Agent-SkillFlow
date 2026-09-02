from pathlib import Path
from types import SimpleNamespace

import pytest

from skillflow.experiment.t16.provider import TokenUsage
from skillflow.experiment.t17 import campaign_reporting
from skillflow.experiment.t17.comparison_models import (
    T17CrossModelReport,
    T17Direction,
)
from skillflow.experiment.t17.contracts import (
    EvidenceDomain,
    EvidenceDomainKind,
    MeasurementStatus,
    RatioMeasurement,
)
from skillflow.experiment.t17.cross_model_report import (
    _interval_direction,
    _point_direction,
    write_cross_model_report,
)
from skillflow.experiment.t17.defense_models import T17DefenseReport
from skillflow.experiment.t17.defense_report import (
    T17DefenseReportError,
    _gain,
    _over_defense_rate,
    _ratio_value,
    _security_gains,
    _total_tokens,
)
from skillflow.experiment.t17.final_models import T17FinalMetricsReport
from skillflow.experiment.t17.final_report import (
    T17FinalReportWriteError,
    _write_summary_csv,
    build_final_metrics_report,
    write_final_metrics_report,
)
from skillflow.experiment.t17.live_attempt_models import T17LiveStageSummary
from skillflow.experiment.t17.live_matrix import T17LiveStage
from skillflow.experiment.t17.metric_models import (
    T17CausalImpactSummary,
    T17IntervalEstimate,
    T17IntervalMethod,
    T17PhaseMetricsReport,
    T17UeaSummary,
)


def _ratio(value: float = 0.5) -> RatioMeasurement:
    return RatioMeasurement(
        status=MeasurementStatus.MEASURED,
        numerator=round(value * 100),
        denominator=100,
        scheduled_denominator=100,
        value=value,
    )


def _interval(point: float, lower: float, upper: float) -> T17IntervalEstimate:
    return T17IntervalEstimate(
        status=MeasurementStatus.MEASURED,
        method=T17IntervalMethod.CLUSTER_BOOTSTRAP,
        point=point,
        lower=lower,
        upper=upper,
        resamples=10_000,
        seed=17_017,
    )


def _domain(revision: str) -> EvidenceDomain:
    return EvidenceDomain(
        domain_id=f"domain-{revision}",
        kind=EvidenceDomainKind.REFERENCE_HARNESS,
        simulation_only=False,
        external_effects_simulated=True,
        protocol_id="t17-live-reference-v1",
        provider="openai",
        model_id=revision,
        model_revision=revision,
    )


def _phase(
    stage: T17LiveStage,
    revision: str,
    interval: T17IntervalEstimate | None = None,
) -> T17PhaseMetricsReport:
    ratio = _ratio()
    return T17PhaseMetricsReport.model_construct(
        required_metrics_complete=True,
        evidence_domain=_domain(revision),
        task_success_rate=ratio,
        safe_task_success_rate=ratio,
        benign_refusal_rate=ratio,
        verified_target_effect_rate=ratio,
        uea=T17UeaSummary.model_construct(affected_trial_rate=ratio),
        causal_impact=T17CausalImpactSummary.model_construct(nonzero_rate=ratio),
        bootstrap_intervals={"delta": interval or _interval(0.2, 0.1, 0.3)},
        stage_summary=T17LiveStageSummary.model_construct(
            stage=stage,
            completion=ratio,
        ),
        cluster_consistency=ratio,
    )


def _patch_phase_loader(
    monkeypatch: pytest.MonkeyPatch,
    phases: list[T17PhaseMetricsReport],
) -> None:
    iterator = iter(phases)
    monkeypatch.setattr(
        T17PhaseMetricsReport,
        "model_validate_json",
        classmethod(lambda _cls, _raw: next(iterator)),
    )


def test_cross_model_writer_preserves_independent_denominators(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model1_path = tmp_path / "model1.json"
    model2_path = tmp_path / "model2.json"
    model1_path.write_text("{}\n", encoding="utf-8")
    model2_path.write_text("{}\n", encoding="utf-8")
    _patch_phase_loader(
        monkeypatch,
        [
            _phase(T17LiveStage.MODEL1, "model-1", _interval(0.2, 0.1, 0.3)),
            _phase(T17LiveStage.MODEL2, "model-2", _interval(0.4, 0.2, 0.6)),
        ],
    )
    output = tmp_path / "cross.json"

    report = write_cross_model_report(model1_path, model2_path, output)

    assert report.complete is True
    assert len(report.side_by_side_ratios) == 6
    assert report.point_direction_agreement.value == 1.0
    assert report.robust_direction_agreement.value == 1.0
    assert output.is_file()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, T17Direction.INDETERMINATE),
        (-0.1, T17Direction.NEGATIVE),
        (0.0, T17Direction.ZERO),
        (0.1, T17Direction.POSITIVE),
    ],
)
def test_point_direction_covers_all_states(
    value: float | None,
    expected: T17Direction,
) -> None:
    assert _point_direction(value) is expected


@pytest.mark.parametrize(
    ("lower", "upper", "expected"),
    [
        (None, 1.0, T17Direction.INDETERMINATE),
        (-2.0, -0.1, T17Direction.NEGATIVE),
        (0.1, 2.0, T17Direction.POSITIVE),
        (-0.1, 0.1, T17Direction.INDETERMINATE),
    ],
)
def test_interval_direction_covers_all_states(
    lower: float | None,
    upper: float | None,
    expected: T17Direction,
) -> None:
    assert _interval_direction(lower, upper) is expected


def test_final_report_writer_emits_json_and_long_csv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    phase_paths = tuple(tmp_path / f"phase-{index}.json" for index in range(5))
    for path in phase_paths:
        path.write_text("{}\n", encoding="utf-8")
    cross_path = tmp_path / "cross.json"
    defense_path = tmp_path / "defense.json"
    cross_path.write_text("{}\n", encoding="utf-8")
    defense_path.write_text("{}\n", encoding="utf-8")
    phases = [
        _phase(stage, "model")
        for stage in (
            T17LiveStage.CANARY,
            T17LiveStage.MODEL1,
            T17LiveStage.MODEL2_CANARY,
            T17LiveStage.MODEL2,
            T17LiveStage.DEFENSE,
        )
    ]
    _patch_phase_loader(monkeypatch, phases)
    monkeypatch.setattr(
        T17CrossModelReport,
        "model_validate_json",
        classmethod(lambda _cls, _raw: T17CrossModelReport.model_construct(complete=True)),
    )
    monkeypatch.setattr(
        T17DefenseReport,
        "model_validate_json",
        classmethod(lambda _cls, _raw: T17DefenseReport.model_construct(complete=True)),
    )
    json_output = tmp_path / "final.json"
    csv_output = tmp_path / "final.csv"

    report = write_final_metrics_report(
        phase_paths,
        cross_path,
        defense_path,
        json_output,
        csv_output,
    )

    assert report.complete is True
    assert json_output.is_file()
    assert len(csv_output.read_text(encoding="utf-8").splitlines()) == 41
    with pytest.raises(T17FinalReportWriteError):
        _write_summary_csv(csv_output, report)
    assert str(T17FinalReportWriteError("final.csv")) == ("final_report_write_failed:final.csv")


def test_final_report_marks_wrong_phase_count_incomplete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    phase_paths = tuple(tmp_path / f"phase-{index}.json" for index in range(4))
    for path in (*phase_paths, tmp_path / "cross.json", tmp_path / "defense.json"):
        path.write_text("{}\n", encoding="utf-8")
    _patch_phase_loader(
        monkeypatch,
        [_phase(T17LiveStage.CANARY, "model") for _ in phase_paths],
    )
    monkeypatch.setattr(
        T17CrossModelReport,
        "model_validate_json",
        classmethod(lambda _cls, _raw: T17CrossModelReport.model_construct(complete=True)),
    )
    monkeypatch.setattr(
        T17DefenseReport,
        "model_validate_json",
        classmethod(lambda _cls, _raw: T17DefenseReport.model_construct(complete=True)),
    )

    report = build_final_metrics_report(
        phase_paths,
        tmp_path / "cross.json",
        tmp_path / "defense.json",
    )

    assert report.complete is False


def _stage_view(stage: T17LiveStage, root: Path) -> SimpleNamespace:
    return SimpleNamespace(prepared=SimpleNamespace(stage=stage, attempt_root=root / stage.value))


def test_campaign_reporting_routes_model2_and_defense(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stages = tuple(_stage_view(stage, tmp_path) for stage in T17LiveStage)
    context = campaign_reporting.T17CampaignReportingContext(
        tmp_path,
        tmp_path / "campaign",
        stages,
    )
    calls: list[str] = []
    monkeypatch.setattr(
        campaign_reporting,
        "write_cross_model_report",
        lambda *_args: calls.append("cross"),
    )
    monkeypatch.setattr(
        campaign_reporting,
        "write_defense_report",
        lambda *_args: calls.append("defense"),
    )
    final = T17FinalMetricsReport.model_construct(complete=True)
    monkeypatch.setattr(
        campaign_reporting,
        "write_final_metrics_report",
        lambda *_args: calls.append("final") or final,
    )

    assert (
        campaign_reporting.update_campaign_reports(
            context,
            _stage_view(T17LiveStage.CANARY, tmp_path),
        )
        is None
    )
    assert (
        campaign_reporting.update_campaign_reports(
            context,
            _stage_view(T17LiveStage.MODEL2, tmp_path),
        )
        is None
    )
    assert (
        campaign_reporting.update_campaign_reports(
            context,
            _stage_view(T17LiveStage.DEFENSE, tmp_path),
        )
        is final
    )
    assert calls == ["cross", "defense", "final"]


def test_campaign_reporting_rejects_missing_stage(tmp_path: Path) -> None:
    context = campaign_reporting.T17CampaignReportingContext(
        tmp_path,
        tmp_path / "campaign",
        (),
    )
    result = _stage_view(T17LiveStage.MODEL2, tmp_path)

    with pytest.raises(campaign_reporting.T17SupervisorSequenceError) as captured:
        campaign_reporting.update_campaign_reports(context, result)

    assert str(captured.value) == "t17_stage_missing:model1"


def test_defense_helpers_cover_missing_and_measured_values() -> None:
    missing = _gain("risk", None, 0.1)
    measured = _gain("risk", 0.8, 0.3)
    assert missing.status is MeasurementStatus.NOT_AVAILABLE
    assert measured.security_gain == pytest.approx(0.5)
    assert _ratio_value(_ratio(0.25)) == 0.25
    with pytest.raises(T17DefenseReportError):
        _ratio_value(
            RatioMeasurement(
                status=MeasurementStatus.NOT_APPLICABLE,
                reason="no denominator",
            )
        )
    mode = SimpleNamespace(
        telemetry=SimpleNamespace(
            token_usage=TokenUsage(
                input_tokens=10,
                cached_input_tokens=0,
                output_tokens=3,
                reasoning_tokens=2,
            )
        )
    )
    assert _total_tokens(mode) == 15
    assert _over_defense_rate((), {}, {}).status is MeasurementStatus.NOT_APPLICABLE


def test_security_gains_include_hiaa_and_residual_metrics() -> None:
    def fake_mode(value: float) -> SimpleNamespace:
        return SimpleNamespace(
            risk_vte_rate=_ratio(value),
            risk_uea_affected_rate=_ratio(value),
            standard_risk_report=SimpleNamespace(
                alr=SimpleNamespace(value=value),
                rir_1=SimpleNamespace(value=value),
                rir_3=SimpleNamespace(value=value),
                hiaa_designs=(
                    SimpleNamespace(
                        design_id="c1",
                        hiaa_run=SimpleNamespace(value=value),
                    ),
                ),
            ),
        )

    gains = _security_gains(fake_mode(0.8), fake_mode(0.2))

    assert {item.metric for item in gains} == {
        "risk_vte_rate",
        "risk_uea_affected_rate",
        "alr",
        "rir_1",
        "rir_3",
        "hiaa_run:c1",
    }
    assert all(item.security_gain == pytest.approx(0.6) for item in gains)
