from dataclasses import replace
from pathlib import Path

import pytest

from skillflow.experiment.t18.dataset import export_dataset, load_dataset, recompute_dataset
from skillflow.experiment.t18.report_data import AnalysisData, validate_data
from skillflow.experiment.t18.reporting import build_report

ROOT = Path(__file__).resolve().parents[3]
PUBLIC = ROOT / "datasets/t18-local/fake_reference"


@pytest.fixture(scope="module")
def data() -> AnalysisData:
    return load_dataset(PUBLIC)


def test_public_data_contains_complete_hiaa_and_real_failures(data: AnalysisData) -> None:
    report = build_report(data)
    assert (report.completed_core, report.replay_pairs) == (44, 5)
    assert report.status == "measured"
    assert len(report.hiaa) == 4
    assert all(h.status == "measured" for h in report.hiaa)
    assert report.vectors["all_scheduled"]["api_calls"].value == 0


def test_export_is_idempotent_and_independently_recomputable(
    data: AnalysisData, tmp_path: Path
) -> None:
    destination = tmp_path / "public"
    first = export_dataset(data, destination)
    assert export_dataset(data, destination) == first
    assert load_dataset(destination) == data
    result = recompute_dataset(destination, tmp_path / "recomputed")
    assert result["status"] == "pass"
    assert result["compared_files"] == 3
    manifest = destination / "manifest.json"
    manifest.write_text(manifest.read_text(encoding="utf-8") + " ", encoding="utf-8")
    assert load_dataset(destination) == data


def test_duplicate_or_cross_domain_core_is_rejected(data: AnalysisData) -> None:
    with pytest.raises(ValueError, match="duplicate_core"):
        validate_data(replace(data, cores=(*data.cores, data.cores[0])), verify=False)
    first = data.cores[0].model_copy(update={"domain": "scripted"})
    with pytest.raises(ValueError, match="phase_binding"):
        validate_data(replace(data, cores=(first, *data.cores[1:])), verify=False)


def test_missing_replay_cannot_be_reported_as_zero(data: AnalysisData) -> None:
    with pytest.raises(ValueError, match="missing_replay"):
        validate_data(replace(data, replays=data.replays[1:]), verify=False)
