import json
from dataclasses import replace
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skillflow.cli import app
from skillflow.experiment.t18.dataset import export_dataset, load_dataset
from skillflow.experiment.t18.report_data import AnalysisData
from skillflow.experiment.t18.table_models import TableManifest
from skillflow.experiment.t18.tables import TABLE_NAMES, recompute_collection, write_tables

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def data() -> AnalysisData:
    return load_dataset(ROOT / "datasets/t18-local/fake_reference")


def test_named_delivery_tables_preserve_facts_and_actual_authorization(
    data: AnalysisData, tmp_path: Path
) -> None:
    manifest = write_tables((data,), tmp_path)
    assert set(manifest.files) == set(TABLE_NAMES)
    assert manifest.files["core-trials.jsonl"].records == 44
    assert manifest.files["replay-pairs.jsonl"].records == 5
    outcomes = [
        json.loads(line)
        for line in (tmp_path / "defense-outcomes.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(outcomes) == 34
    assert all(row["domain"] == "fake_reference" for row in outcomes)
    assert any(False in row["outcome"]["before_authorization"] for row in outcomes)
    assert all(
        row["outcome"]["safe_task_success"]
        == (row["outcome"]["task_success"] and not row["outcome"]["residual_risk"])
        for row in outcomes
    )
    by_run = {core.run_id: core for core in data.cores}
    for row in outcomes:
        outcome = row["outcome"]
        for side in ("before", "after"):
            core = by_run[outcome[side + "_run_id"]]
            assert core.data is not None
            actual = {d.decision_id: d.authorized for d in core.data.facts.decisions}
            effects = [e for e in core.data.facts.effects if e.executed]
            assert outcome[side + "_effect_ids"] == [e.effect_id for e in effects]
            assert outcome[side + "_authorization"] == [actual[e.decision_id] for e in effects]
            assert all(e.tool_receipt_id in outcome["evidence_ids"] for e in effects)
    plans = [
        json.loads(line)
        for line in (tmp_path / "defense-plans.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(plans) == sum(len(core.traces) for core in data.cores)
    assert any(p["actual_defense_ids"] != p["proposed_plan"]["selected_defense_ids"] for p in plans)
    for plan in plans:
        trace = next(
            t
            for t in by_run[plan["run_id"]].traces
            if t.request_event_id == plan["request_event_id"]
        )
        assert plan["actual_defense_ids"] == list(trace.selected)
        assert plan["authorized"] == trace.base_authorized
        assert plan["executed"] == trace.final_executed
    assert write_tables((data,), tmp_path) == manifest


def test_tables_reject_missing_or_duplicate_domains(data: AnalysisData, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="duplicate_or_empty"):
        write_tables((data, data), tmp_path)
    with pytest.raises(ValueError, match="duplicate_or_empty"):
        write_tables((), tmp_path)
    with pytest.raises(ValueError, match="incomplete"):
        write_tables((replace(data, cores=data.cores[1:]),), tmp_path)


def test_tables_refuse_overwriting_other_results(data: AnalysisData, tmp_path: Path) -> None:
    (tmp_path / "core-trials.jsonl").write_text("other result\n", encoding="utf-8")
    with pytest.raises(ValueError, match="existing_content_differs"):
        write_tables((data,), tmp_path)
    assert (tmp_path / "core-trials.jsonl").read_text(encoding="utf-8") == "other result\n"


def test_collection_cli_recomputes_tables_and_rejects_tampering(
    data: AnalysisData, tmp_path: Path
) -> None:
    public = tmp_path / "public"
    export_dataset(data, public / data.phase.domain)
    write_tables((data,), public)
    result = CliRunner().invoke(
        app,
        ["defense", "report", "--dataset", str(public), "--output", str(tmp_path / "recomputed")],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["compared_files"] == 13
    with pytest.raises(ValueError, match="separate_output"):
        recompute_collection(public, public / "not-allowed")
    diagnoses = public / "diagnoses.jsonl"
    diagnoses.write_text(diagnoses.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="recompute_mismatch:diagnoses"):
        recompute_collection(public, tmp_path / "tampered")
    path = public / "sha256-manifest.json"
    manifest = TableManifest.model_validate_json(path.read_text(encoding="utf-8"))
    entry = manifest.files["core-trials.jsonl"]
    manifest.files["core-trials.jsonl"] = entry.model_copy(update={"records": entry.records + 1})
    path.write_text(manifest.model_dump_json(), encoding="utf-8")
    with pytest.raises(ValueError, match="manifest_mismatch"):
        recompute_collection(public, tmp_path / "manifest-tampered")
