import json
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError

from skillflow.experiment.t18.core_metrics import core_metrics, core_values
from skillflow.experiment.t18.dataset import load_dataset
from skillflow.experiment.t18.metric_models import Measure, measure
from skillflow.experiment.t18.report_data import AnalysisData, hiaa_trials, validate_data
from skillflow.experiment.t18.reporting import build_report, write_report
from skillflow.experiment.t18.run_models import LocalCore
from skillflow.experiment.t18.schema_models import t18_schema_documents, write_t18_schemas

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def data() -> AnalysisData:
    return load_dataset(ROOT / "datasets/t18-local/fake_reference", verify=False)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"value": 2}, "arithmetic"),
        ({"denominator": -1}, "negative_denominator"),
        ({"denominator": 0}, "arithmetic"),
        ({"status": "incomplete"}, "unmeasured_value"),
        ({"status": "not_applicable"}, "unmeasured_value"),
    ],
)
def test_metric_rejects_fabricated_values(changes: dict[str, object], message: str) -> None:
    payload = measure(1, 2, ("run",)).model_dump(mode="json")
    payload.update(changes)
    with pytest.raises(ValidationError, match=message):
        Measure.model_validate(payload)


def test_missing_sample_preserves_scheduled_denominator(data: AnalysisData) -> None:
    sample = next(
        c for c in data.cores if c.cell.trial_id in data.matrix.hiaa_groups[0].cells.values()
    )
    subset = replace(data, cores=tuple(c for c in data.cores if c != sample))
    report = build_report(subset)
    assert report.status == "incomplete"
    assert report.vectors["all_scheduled"]["task_success"].denominator == 44
    assert report.vectors["all_scheduled"]["task_success"].value is None
    assert any(h.status == "incomplete" for h in report.hiaa)


def test_metrics_count_receipted_effects_not_skill_names(data: AnalysisData) -> None:
    monitor = data.select(lambda c: c.mode == "monitor" and c.bridge_enabled)
    values = core_metrics(monitor)
    actual_task = sum(c.data.proof.task.task_success for c in monitor.cores if c.data)
    actual_uea = sum(
        sum(not d.authorized and d.executed for d in c.data.facts.decisions)
        for c in monitor.cores
        if c.data
    )
    assert values["task_success"].numerator == actual_task
    assert values["uea_count"].value == actual_uea
    assert values["binding_coverage"].value == 1
    assert values["receipt_coverage"].value == 1


def test_invalid_terminal_cannot_contribute_zero_success(data: AnalysisData) -> None:
    first = data.cores[0].model_copy(
        update={
            "status": "infrastructure_invalid",
            "data": None,
            "failure_reason": "fixture_failure",
        }
    )
    assert core_values(first) == {}
    report = core_metrics(replace(data, cores=(first, *data.cores[1:])))
    assert report["infrastructure_failure"].numerator == 1
    assert report["task_success"].status == "incomplete"
    assert not hiaa_trials(replace(data, cores=(first,)))[0].valid


def test_formal_terminal_rejects_authorization_rewrite(data: AnalysisData) -> None:
    core = next(c for c in data.cores if c.traces)
    payload = core.model_dump(mode="json")
    payload["traces"][0]["final_authorized"] = not core.traces[0].final_authorized
    with pytest.raises(ValidationError, match="authorization_binding"):
        LocalCore.model_validate(payload)
    payload = core.model_dump(mode="json")
    payload["traces"] = []
    with pytest.raises(ValidationError, match="trace_coverage"):
        LocalCore.model_validate(payload)


def test_report_rejects_phase_and_task_contract_mix(data: AnalysisData) -> None:
    phase = data.phase.model_copy(update={"scheduled_core": 999})
    with pytest.raises(ValueError, match="shared_control_binding"):
        validate_data(replace(data, phase=phase), verify=False)
    core = data.cores[0]
    assert core.data is not None
    altered = core.data.model_copy(update={"task_contract": data.cores[-1].data.task_contract})
    with pytest.raises(ValueError, match="task_contract_binding"):
        validate_data(
            replace(data, cores=(core.model_copy(update={"data": altered}), *data.cores[1:])),
            verify=False,
        )


def test_report_writes_complete_tables_without_overwrite(
    data: AnalysisData, tmp_path: Path
) -> None:
    report = build_report(data)
    write_report(tmp_path, report)
    write_report(tmp_path, report)
    assert (
        json.loads((tmp_path / "metrics.json").read_text(encoding="utf-8"))["status"] == "measured"
    )
    assert "delta_hiaa_valid_only" in (tmp_path / "hiaa.csv").read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="existing_content_differs"):
        write_report(tmp_path, report.model_copy(update={"completed_core": 1}))


def test_schemas_are_typed_and_drift_is_rejected(tmp_path: Path) -> None:
    write_t18_schemas(tmp_path)
    write_t18_schemas(tmp_path)
    assert len(t18_schema_documents()) == 16
    for name, schema in t18_schema_documents():
        assert json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8")) == schema
    (tmp_path / "t18-matrix.schema.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="schema_drift"):
        write_t18_schemas(tmp_path)
