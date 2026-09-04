"""完整固定脚本的独立期望与缺失证据反例。"""

from pathlib import Path

import pytest

from skillflow.experiment.t17.contracts import MeasurementStatus
from skillflow.experiment.t17.live_matrix import T17LiveStage
from skillflow.experiment.t17.v2.analysis_context import AnalysisGroup
from skillflow.experiment.t17.v2.binding import validate_core_binding
from skillflow.experiment.t17.v2.configuration import build_configuration, write_configuration
from skillflow.experiment.t17.v2.dataset_io import export_dataset, load_dataset
from skillflow.experiment.t17.v2.dataset_rows import CoreRow
from skillflow.experiment.t17.v2.loading import load_stage
from skillflow.experiment.t17.v2.matrix import build_matrix
from skillflow.experiment.t17.v2.metrics import metric_vector
from skillflow.experiment.t17.v2.stage import StageSetup, run_stage


@pytest.fixture(scope="module")
def group(t17_cli_root: Path) -> AnalysisGroup:
    root = Path.cwd()
    destination = t17_cli_root / "metric-inputs"
    config, bundles = build_configuration(root, destination)
    write_configuration(root, destination, config, bundles)
    matrix = build_matrix(root, config, T17LiveStage.CANARY)
    result = run_stage(
        StageSetup(root, t17_cli_root / "metric-run", config, matrix, "scripted", None)
    )
    assert result.gate.passed
    return AnalysisGroup(config, result.cores, result.replays)


def test_independent_full_scripted_risk_and_task_goldens(group: AnalysisGroup) -> None:
    values = metric_vector(group)
    assert values["uea_count"].numerator == 8
    assert values["task_success"].numerator == 20
    assert values["safe_task_success"].numerator == 13
    assert values["task_success"].denominator == 24
    for design in ("c1-context-grid", "c2-tool-return-grid"):
        assert values[f"hiaa.{design}.scheduled"].value == 1
    for name in ("alr", "rir_1", "rir_3"):
        assert values[name].numerator == 1, name
        assert values[name].denominator == 2, name
    assert all(
        value.status in {MeasurementStatus.MEASURED, MeasurementStatus.NOT_APPLICABLE}
        for value in values.values()
    )


def test_benign_legitimate_effects_do_not_count_as_attacks(group: AnalysisGroup) -> None:
    benign = group.select(tuple(c for c in group.cores if c.data.task_contract.benign_control))
    values = metric_vector(benign)
    assert values["verified_target_effect"].numerator == 0
    assert values["uea_count"].numerator == 0


def test_incomplete_core_keeps_scheduled_denominator(group: AnalysisGroup) -> None:
    incomplete = group.cores[-1].model_copy(
        update={"status": "not_run", "reason": "attempt_interrupted", "data": None, "run_id": None}
    )
    partial = AnalysisGroup(group.configuration, (*group.cores[:-1], incomplete), group.replays)
    value = metric_vector(partial)["task_success"]
    assert value.status is MeasurementStatus.INCOMPLETE
    assert value.value is None
    assert value.scheduled_denominator == 24


def test_canary_bootstrap_not_available_is_never_used(group: AnalysisGroup) -> None:
    value = metric_vector(group)["task_success"]
    assert value.intervals[1].status is MeasurementStatus.NOT_APPLICABLE
    assert value.intervals[1].complete_clusters == 1


def test_registered_claim_and_session_contrasts_use_actual_pairs(group: AnalysisGroup) -> None:
    values = metric_vector(group)
    assert values["claim_neutralized"].value == 1
    for offset in (1, 3):
        key = f"session_pair.pair-m2-residual.{offset}"
        assert values[key].value == 1
        assert values[key + ".target"].numerator == 1
        assert values[key + ".control"].numerator == 0
        assert values[key].intervals[0].status is MeasurementStatus.NOT_APPLICABLE


def test_paired_metrics_do_not_use_attack_family_labels(group: AnalysisGroup) -> None:
    variants = tuple(
        v.model_copy(update={"attack_family": "unrelated-label"})
        for v in group.configuration.catalog.variants
    )
    catalog = group.configuration.catalog.model_copy(update={"variants": variants})
    config = group.configuration.model_copy(update={"catalog": catalog})
    assert metric_vector(AnalysisGroup(config, group.cores, group.replays)) == metric_vector(group)


def test_saved_stage_round_trip_recomputes_all_measurements(
    group: AnalysisGroup, t17_cli_root: Path
) -> None:
    loaded = load_stage(Path.cwd(), t17_cli_root / "metric-run")
    assert loaded.result.gate.passed
    assert metric_vector(loaded.group()) == metric_vector(group)


def test_terminal_identity_forgery_is_rejected(group: AnalysisGroup) -> None:
    core = group.cores[0]
    forged = core.model_copy(
        update={"identity": core.identity.model_copy(update={"skill_content_sha256": "0" * 64})}
    )
    with pytest.raises(ValueError, match="identity"):
        validate_core_binding(group.configuration, forged)


def test_public_dataset_recomputes_without_private_raw(
    group: AnalysisGroup, t17_cli_root: Path
) -> None:
    loaded = load_stage(Path.cwd(), t17_cli_root / "metric-run")
    output = t17_cli_root / "public-dataset"
    manifest = export_dataset(Path.cwd(), output, (loaded,))
    assert manifest.scheduled_core == 24
    assert manifest.scheduled_replay == 18
    assert manifest.full_project_completion_claim is False
    restored = load_dataset(output)
    assert len(restored) == 1
    assert metric_vector(restored[0].group()) == metric_vector(group)
    for filename in (
        "core-trials.jsonl",
        "replay-pairs.jsonl",
        "task-success-evidence.jsonl",
        "effect-receipts.jsonl",
        "provenance-edges.jsonl",
        "metrics-long.csv",
        "condition-summary.csv",
        "model-comparison.csv",
        "defense-comparison.csv",
        "skill-comparison-ready.csv",
        "sha256-manifest.json",
    ):
        assert (output / filename).is_file()


def test_exported_fact_rejects_a_changed_proof_hash(group: AnalysisGroup) -> None:
    row = CoreRow.from_terminal(group.cores[0])
    forged = row.model_copy(update={"proof_sha256": "0" * 64})
    with pytest.raises(ValueError, match="proof_drift"):
        forged.restore()


def test_missing_claim_replay_is_incomplete_not_an_exception(group: AnalysisGroup) -> None:
    core = next(c for c in group.cores if c.data is not None and c.data.claim_bindings)
    pair = next(r for r in group.replays if r.source_core_run_id == core.run_id)
    failed = pair.model_copy(update={"status": "not_run", "reason": "interrupted", "proof": None})
    replays = tuple(
        failed if r.identity.unit_id == pair.identity.unit_id else r for r in group.replays
    )
    value = metric_vector(AnalysisGroup(group.configuration, group.cores, replays))["alr"]
    assert value.status is MeasurementStatus.INCOMPLETE
    assert value.value is None
    assert value.denominator == 2


def test_unfinished_four_cell_cannot_be_design_not_applicable(group: AnalysisGroup) -> None:
    selected = group.select(
        tuple(c for c in group.cores if group.variant(c).hiaa_design_id == "c1-context-grid")
    )
    failed = selected.cores[0].model_copy(
        update={"status": "not_run", "reason": "interrupted", "data": None, "run_id": None}
    )
    partial = AnalysisGroup(group.configuration, (failed, *selected.cores[1:]), selected.replays)
    assert (
        metric_vector(partial)["hiaa.c1-context-grid.valid_only"].status
        is MeasurementStatus.INCOMPLETE
    )
