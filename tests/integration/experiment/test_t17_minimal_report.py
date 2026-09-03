from pathlib import Path

import pytest
from typer.testing import CliRunner

from skillflow.cli import app
from skillflow.experiment.inputs import apply_variant, namespace_grants
from skillflow.experiment.t17.contracts import MeasurementStatus
from skillflow.experiment.t17.minimal import raw_loader
from skillflow.experiment.t17.minimal.raw_bindings import verify_record_bindings
from skillflow.experiment.t17.minimal.raw_core import verify_core_record
from skillflow.experiment.t17.minimal.raw_loader import MinimalDomainData, load_minimal_domain
from skillflow.experiment.t17.minimal.report_models import MinimalDomainReport
from skillflow.experiment.t17.minimal.reporting import build_minimal_report
from skillflow.experiment.t17.minimal.run_models import MinimalRunRecord
from skillflow.models.scenario import Scenario
from skillflow.store.sqlite_store import SqliteEventStore
from skillflow.validation import validate_yaml_document


@pytest.fixture(scope="module")
def minimal_report_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("minimal-report")
    runner = CliRunner()
    frozen = runner.invoke(app, ["t17", "minimal", "freeze", "--output", str(root / "inputs")])
    assert frozen.exit_code == 0, frozen.output
    result = runner.invoke(
        app,
        [
            "t17",
            "minimal",
            "run",
            "--configuration",
            str(root / "inputs" / "preregistration.yaml"),
            "--output",
            str(root / "fake-report"),
            "--domain",
            "fake_reference",
        ],
    )
    assert result.exit_code == 0, result.output
    return root / "fake-report" / "execution"


@pytest.fixture(scope="module")
def verified_data(minimal_report_root: Path) -> MinimalDomainData:
    return load_minimal_domain(minimal_report_root)


def test_report_recomputes_all_metrics_from_raw(minimal_report_root: Path) -> None:
    report = build_minimal_report(minimal_report_root)
    assert report.technical_gate_passed
    assert report.observed_core_runs == 23
    assert report.observed_replay_pairs == 12
    assert {item.status for item in report.metrics.values()} <= {
        MeasurementStatus.MEASURED,
        MeasurementStatus.NOT_APPLICABLE,
    }
    assert report.metrics["task_success"].numerator == 20
    assert report.metrics["safe_task_success"].numerator == 13
    assert report.metrics["uea_count"].value == 8
    assert report.metrics["alr"].value == 0.5
    assert report.metrics["rir_1"].value == report.metrics["rir_3"].value == 0.5
    assert report.metrics["hiaa.c1-context-grid.scheduled"].value == 1.0
    assert report.metrics["hiaa.c1-context-grid.valid_only"].value == 1.0
    assert report.metrics["hiaa.c2-tool-return-grid.valid_only"].value == 1.0
    assert report.metrics["receipt_coverage"].value == 1
    assert report.metrics["task_evidence_coverage"].value == 1
    assert report.metrics["required_hook_coverage"].value == 1
    assert report.metrics["actual_api_calls"].value == 0
    assert report.defense["security_gain.uea_count"].value == 1
    assert report.defense["utility_loss.benign"].value == 0
    assert report.defense["over_defense"].value == 0
    assert report.metrics["bootstrap_ci"].status is MeasurementStatus.NOT_APPLICABLE
    assert all(
        item.evidence_ids
        for item in report.metrics.values()
        if item.status is MeasurementStatus.MEASURED
    )


def test_cli_report_writes_static_valid_non_overwriting_json_csv(
    minimal_report_root: Path, tmp_path: Path
) -> None:
    output = tmp_path / "report.json"
    args = ["t17", "minimal", "report", "--raw", str(minimal_report_root), "--output", str(output)]
    runner = CliRunner()
    first = runner.invoke(app, args)
    assert first.exit_code == 0, first.output
    assert output.with_suffix(".csv").is_file()
    assert MinimalDomainReport.model_validate_json(
        output.read_text(encoding="utf-8")
    ).technical_gate_passed
    assert runner.invoke(app, args).exit_code == 2
    inside = runner.invoke(app, [*args[:-1], str(minimal_report_root / "forbidden.json")])
    assert inside.exit_code == 2
    assert not (minimal_report_root / "forbidden.json").exists()


@pytest.mark.parametrize("field", ["uea_count", "task_success", "alr", "rir_3"])
def test_report_cannot_omit_required_metrics(minimal_report_root: Path, field: str) -> None:
    report = build_minimal_report(minimal_report_root)
    document = report.model_dump()
    document["metrics"].pop(field)
    with pytest.raises(ValueError, match="required_metric_missing"):
        MinimalDomainReport.model_validate(document)


@pytest.mark.parametrize("mutation", ["phase", "domain", "duplicate"])
def test_loader_rejects_cross_phase_domain_and_duplicate_run(
    minimal_report_root: Path,
    verified_data: MinimalDomainData,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    original = raw_loader.read_model
    selected = verified_data.records[0]
    changes: dict[str, object] = {
        "phase_contract_sha256": "f" * 64,
    }
    if mutation == "domain":
        changes = {"domain": "scripted"}
    elif mutation == "duplicate":
        changes = {"run_id": verified_data.records[1].run_id}
    altered = selected.model_copy(update=changes)
    monkeypatch.setattr(
        raw_loader,
        "read_model",
        lambda path, model: (
            altered
            if model is MinimalRunRecord and path.parent.name == selected.run_id
            else original(path, model)
        ),
    )
    with pytest.raises(ValueError, match=r"cross_domain_or_phase|duplicate_core"):
        load_minimal_domain(minimal_report_root)


@pytest.mark.parametrize("mutation", ["step", "hook", "journal"])
def test_runtime_rejects_forged_step_hook_and_fake_journal(
    minimal_report_root: Path,
    verified_data: MinimalDomainData,
    mutation: str,
) -> None:
    record = next(item for item in verified_data.records if item.variant == "b0-monitor")
    changes: dict[str, object] = {"step_event_ids": ("forged-step",)}
    if mutation == "hook":
        changes = {"hooks": ()}
    elif mutation == "journal":
        changes = {
            "decision_journal": (record.decision_journal[0].model_copy(update={"sequence": 99}),)
        }
    variant = next(
        item
        for item in verified_data.configuration.matrix.variants
        if item.variant == record.variant
    )
    scenario = namespace_grants(
        apply_variant(validate_yaml_document(Path(variant.scenario.root), Scenario), variant),
        record.run_id,
    )
    with (
        SqliteEventStore(minimal_report_root / "state.sqlite") as store,
        pytest.raises(
            ValueError, match=r"step_event_binding|hook_evidence_binding|fake_journal_binding"
        ),
    ):
        verify_record_bindings(store, record.model_copy(update=changes), scenario)


def test_raw_recompute_rejects_alias_forgery(
    minimal_report_root: Path, verified_data: MinimalDomainData
) -> None:
    record = verified_data.records[0].model_copy(
        update={"artifact_ids_by_alias": {"invented": "forged-id"}}
    )
    with pytest.raises(ValueError, match="alias_trace_binding"):
        verify_core_record(minimal_report_root, record, verified_data.configuration, Path())


def test_cli_invalid_domain_stops_without_creating_run(
    minimal_report_root: Path, tmp_path: Path
) -> None:
    config = minimal_report_root.parent.parent / "inputs" / "preregistration.yaml"
    args = [
        "t17",
        "minimal",
        "run",
        "--configuration",
        str(config),
        "--output",
        str(tmp_path / "not-created"),
        "--domain",
        "live",
    ]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 2
    assert not (tmp_path / "not-created").exists()
