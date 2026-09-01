"""T16-B 双 Fake Slot 全矩阵调度与证据编排。"""

from dataclasses import dataclass
from pathlib import Path

from skillflow.experiment.t16.dry_run_checks import (
    build_cost_simulation_report,
    run_failure_injection_report,
)
from skillflow.experiment.t16.dry_run_execution import execute_fake_matrix
from skillflow.experiment.t16.dry_run_integrity import (
    DuplicateTrialError,
    build_matrix_integrity_report,
)
from skillflow.experiment.t16.dry_run_io import DryRunResultStore, sha256_path, write_json_model
from skillflow.experiment.t16.dry_run_records import load_t16b_config
from skillflow.experiment.t16.dry_run_reports import (
    AttackSuccessRateStatus,
    ExternalReviewStatus,
    T16BDryRunSummary,
)
from skillflow.experiment.t16.matrix import (
    load_matrix,
    validate_matrix_against_preregistration,
)
from skillflow.experiment.t16.preregistration import load_preregistration

__all__ = [
    "DryRunRequest",
    "DuplicateTrialError",
    "build_matrix_integrity_report",
    "execute_fake_matrix",
    "execute_t16b",
]


@dataclass(frozen=True, slots=True)
class DryRunRequest:
    """一次不可覆盖 T16-B 执行的三个受控根。"""

    project_root: Path
    output_root: Path
    evidence_root: Path


def execute_t16b(request: DryRunRequest) -> T16BDryRunSummary:
    """执行 720 链、故障/费用演练并写出四份不可覆盖证据。"""
    t16_root = request.project_root / "experiments" / "t16"
    registration = load_preregistration(t16_root / "preregistration.yaml")
    matrix = load_matrix(t16_root / "matrix_model1.yaml")
    config = load_t16b_config(t16_root / "t16b_fake_dry_run.yaml")
    validate_matrix_against_preregistration(matrix, registration)
    records = execute_fake_matrix(registration, matrix, config)
    request.output_root.mkdir(parents=True, exist_ok=False)
    trial_path = request.output_root / "trial-results.jsonl"
    store = DryRunResultStore(trial_path)
    store.initialize()
    for record in records:
        store.append(record)
    matrix_report = build_matrix_integrity_report(registration, records)
    failure_report = run_failure_injection_report(config, records)
    cost_report = build_cost_simulation_report(
        config,
        records[:3],
        request.output_root / "budget-stop-results.jsonl",
    )
    summary = T16BDryRunSummary(
        id=config.id,
        real_attack_success_rate_status=AttackSuccessRateStatus.NOT_APPLICABLE,
        external_review_status=ExternalReviewStatus.REVIEW_UNAVAILABLE,
        model_slots=(config.slots[0].slot_id, config.slots[1].slot_id),
        trial_results_artifact=f"runs/{request.output_root.name}/trial-results.jsonl",
        trial_results_sha256=sha256_path(trial_path),
        matrix_integrity=matrix_report,
        failure_injection=failure_report,
        cost_simulation=cost_report,
    )
    request.evidence_root.mkdir(parents=True, exist_ok=True)
    write_json_model(request.evidence_root / "t16b-matrix-integrity.json", matrix_report)
    write_json_model(request.evidence_root / "t16b-failure-injection.json", failure_report)
    write_json_model(request.evidence_root / "t16b-cost-simulation.json", cost_report)
    write_json_model(request.evidence_root / "t16b-fake-run-summary.json", summary)
    return summary
