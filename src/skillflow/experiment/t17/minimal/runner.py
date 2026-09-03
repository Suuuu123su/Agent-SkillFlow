"""沿现有 YAML→Runtime→Trace→Graph→Replay 执行最小离线 Matrix。"""

from pathlib import Path

from skillflow.experiment.matrix import (
    MatrixExecutionOutcome,
    MatrixExecutionRequest,
    execute_matrix,
)
from skillflow.experiment.t17.contracts import MeasurementStatus
from skillflow.experiment.t17.minimal.artifacts import (
    build_raw_manifest,
    freeze_phase,
    model_digest,
    validate_configuration,
    write_checked_json,
)
from skillflow.experiment.t17.minimal.contracts import MinimalConfiguration
from skillflow.experiment.t17.minimal.observer import MinimalObservationWriter
from skillflow.experiment.t17.minimal.run_models import MinimalDomain, MinimalExecutionStatus
from skillflow.experiment.t17.minimal.runtime import MinimalHarnessFactory
from skillflow.models.matrix import ExperimentMatrix
from skillflow.validation import validate_yaml_document


def run_minimal_domain(
    configuration_path: Path,
    output_root: Path,
    *,
    domain: MinimalDomain,
    project_root: Path = Path(),
) -> MatrixExecutionOutcome:
    """一次只运行一个域；拒绝旧目录、配置漂移和额外 Replay。"""
    if output_root.exists():
        raise ValueError("minimal_output_exists")
    if domain not in {"scripted", "fake_reference"}:
        raise ValueError("minimal_domain_invalid")
    configuration = validate_configuration(configuration_path, project_root)
    matrix_path = configuration_path.with_name("matrix.yaml")
    matrix = validate_yaml_document(matrix_path, ExperimentMatrix)
    if matrix != configuration.matrix:
        raise ValueError("minimal_matrix_contract_drift")
    phase = freeze_phase(configuration_path, project_root, domain)
    output_root.mkdir(parents=True, exist_ok=False)
    write_checked_json(output_root / "phase-contract.json", phase)
    write_checked_json(output_root / "configuration.json", configuration)
    factory = MinimalHarnessFactory(domain)
    observer = MinimalObservationWriter(configuration, phase, factory)
    execution = output_root / "execution"
    completed = False
    try:
        outcome = execute_matrix(
            MatrixExecutionRequest(
                matrix_path=matrix_path,
                matrix=matrix,
                output=execution,
                determinism_repeats=1,
                redacted=True,
                harness_factory=factory,
                run_observer=observer,
                replay_variants=frozenset(configuration.replay_variants),
                source=configuration.protocol_id,
            )
        )
        _validate_completed(configuration, observer, outcome)
        completed = True
    finally:
        status = MinimalExecutionStatus(
            domain=domain,
            phase_contract_sha256=model_digest(phase),
            status=MeasurementStatus.MEASURED if completed else MeasurementStatus.INCOMPLETE,
            observed_core_runs=len(observer.records),
            observed_replay_pairs=len(tuple((execution / "replays").glob("*/replay-report.json"))),
            reason=None if completed else "run_did_not_complete",
        )
        write_checked_json(output_root / "execution-status.json", status)
        if execution.is_dir():
            write_checked_json(execution / "execution-status.json", status)
            write_checked_json(execution / "phase-contract.json", phase)
            write_checked_json(execution / "configuration.json", configuration)
            write_checked_json(
                execution / "raw-manifest.json", build_raw_manifest(execution, phase)
            )
    return outcome


def _validate_completed(
    configuration: MinimalConfiguration,
    observer: MinimalObservationWriter,
    outcome: MatrixExecutionOutcome,
) -> None:
    if outcome.run_count != len(configuration.matrix.variants):
        raise ValueError("minimal_core_schedule_incomplete")
    if outcome.replay_count != configuration.expected_replay_pairs:
        raise ValueError("minimal_replay_schedule_incomplete")
    golden = {item.variant: item for item in configuration.golden}
    for record in observer.records:
        expected = golden[record.variant]
        actual = (record.task.task_success, record.task.safe_task_success)
        if actual != (expected.task_success, expected.safe_task_success):
            raise ValueError("minimal_task_golden_mismatch:" + record.variant)
