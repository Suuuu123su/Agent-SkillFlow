import json
import math
from pathlib import Path

from skillflow.experiment.t16.task_success_partial_reanalysis import (
    PartialReanalysisPaths,
    build_partial_reanalysis,
)
from skillflow.experiment.t16.task_success_statistics_models import (
    T16D1PartialReanalysis,
)

ROOT = Path(__file__).parents[2]
REPORT_PATH = ROOT / "docs" / "evidence" / "t16c-v2-partial-reanalysis-v0.5-20260829.json"


def _paths() -> PartialReanalysisPaths:
    return PartialReanalysisPaths(
        preregistration=ROOT / "experiments" / "t16" / "preregistration_t16c_v2.yaml",
        smoke_matrix=ROOT / "experiments" / "t16" / "matrix_smoke_t16c_v2.yaml",
        model1_matrix=ROOT / "experiments" / "t16" / "matrix_model1_t16c_v2.yaml",
        model2_subset_matrix=(ROOT / "experiments" / "t16" / "matrix_model2_subset_t16c_v2.yaml"),
        smoke_results=(
            ROOT
            / "runs"
            / "t16c-v2-live-20260829-01"
            / "attempt-01"
            / "smoke"
            / "trial-results.jsonl"
        ),
        model1_results=(
            ROOT
            / "runs"
            / "t16c-v2-live-20260829-01"
            / "attempt-01"
            / "model1"
            / "trial-results.jsonl"
        ),
        v04_reanalysis=(ROOT / "docs" / "evidence" / "t16c-v2-live-reanalysis-v0.4-20260829.json"),
    )


def test_partial_report_is_reproducible_and_keeps_formal_metrics_na() -> None:
    static = T16D1PartialReanalysis.model_validate_json(REPORT_PATH.read_text(encoding="utf-8"))
    rebuilt = build_partial_reanalysis(_paths(), bootstrap_resamples=20_000, seed=20260829)

    assert static == rebuilt
    assert rebuilt.schema_version == "0.5-partial"
    assert rebuilt.record_count == 360
    assert rebuilt.bootstrap.cluster_unit == "semantic_instance_with_all_repeats"
    assert rebuilt.bootstrap.resamples == 20_000
    assert rebuilt.task_success.status == "not_available"
    assert rebuilt.uea.status == "not_available"
    assert rebuilt.alr.status == "not_available"
    assert rebuilt.rir.status == "not_available"
    assert rebuilt.provenance.status == "not_available"
    assert rebuilt.t16d_evidence_acceptance == "BLOCKED"


def test_partial_report_contains_required_point_estimates_and_intervals() -> None:
    report = build_partial_reanalysis(_paths(), bootstrap_resamples=20_000, seed=20260829)
    conditions = {item.condition_id: item for item in report.condition_wilson_intervals}

    assert math.isclose(report.c1_scheduled.hiaa.point_estimate, 14 / 30)
    assert math.isclose(report.c1_valid_sensitivity.hiaa.point_estimate, 2 / 30)
    assert math.isclose(report.m2_session_1.point_estimate, 9 / 30)
    assert math.isclose(report.m2_session_3.point_estimate, 14 / 30)
    assert math.isclose(report.a1_claim_minus_neutralized.point_estimate, 1 / 30)
    assert len(conditions) == 12
    assert (conditions["g0"].successes, conditions["g0"].total) == (30, 30)
    assert (conditions["b0"].successes, conditions["b0"].total) == (0, 30)
    assert all(0 <= item.interval.lower <= item.interval.upper <= 1 for item in conditions.values())


def test_partial_report_contains_only_aggregate_evidence_not_old_task_success() -> None:
    payload = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    rendered = json.dumps(payload, ensure_ascii=False)

    assert "final_summary" not in rendered
    assert "task_success_evidence" not in payload
    assert payload["old_v2_records_modified"] is False
