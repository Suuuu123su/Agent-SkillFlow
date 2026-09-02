from pathlib import Path

from skillflow.benchmark.t12_fixtures import t12_fixture_registry
from skillflow.experiment.matrix import MatrixExecutionRequest, execute_matrix
from skillflow.experiment.t17.contracts import MeasurementStatus
from skillflow.experiment.t17.reference_backend import (
    FakeReferenceModelClient,
    ReferenceModelDecision,
)
from skillflow.experiment.t17.reference_harness import ReferenceHarnessFactory
from skillflow.experiment.t17.run_observer import T17RunObservationWriter
from skillflow.experiment.t17.scenario_registry import (
    load_scenario_measurement_registry,
)
from skillflow.models.matrix import ExperimentMatrix
from skillflow.validation import validate_yaml_document


def test_reference_fake_matrix_completes_24_core_and_18_replays(tmp_path: Path) -> None:
    # Given: a zero-I/O model selecting each fixture's preregistered actions.
    scripts, _ = t12_fixture_registry()
    client = FakeReferenceModelClient(
        {
            root: ReferenceModelDecision(
                selected_action_ids=tuple(item.action_id for item in script.actions),
                output_text=script.output.decode(),
                output_mime_type=script.output_mime_type,
            )
            for root, script in scripts.items()
        }
    )
    factory = ReferenceHarnessFactory(client)
    matrix_path = Path("scenarios/matrix/mvp.yaml")
    matrix = validate_yaml_document(matrix_path, ExperimentMatrix)
    registry = load_scenario_measurement_registry(
        Path("experiments/t17/scenario_measurements.yaml")
    )
    observer = T17RunObservationWriter(registry)

    # When: the existing Matrix and Replay orchestration use the Reference Harness factory.
    result = execute_matrix(
        MatrixExecutionRequest(
            matrix_path=matrix_path,
            matrix=matrix,
            output=tmp_path / "reference-fake",
            determinism_repeats=1,
            redacted=True,
            harness_factory=factory,
            run_observer=observer,
        )
    )

    # Then: the complete technical Canary shape runs without network or missing pairs.
    assert (result.run_count, result.replay_count) == (24, 18)
    assert len(observer.snapshots) == 24
    assert all(
        hook.status is not MeasurementStatus.NOT_AVAILABLE
        for snapshot in observer.snapshots
        for hook in snapshot.hooks
    )
