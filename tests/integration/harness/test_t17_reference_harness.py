from pathlib import Path

import pytest

from skillflow.analysis.facts import RunReportMetadata
from skillflow.benchmark.runner import ScenarioRunLayout, ScenarioRunner, ScenarioRunRequest
from skillflow.benchmark.t12_fixtures import t12_fixture_registry
from skillflow.experiment.t17.contracts import HookName, MeasurementStatus
from skillflow.experiment.t17.observations import (
    ObservationBindingError,
    ReferenceObservationRequest,
    build_reference_observations,
)
from skillflow.experiment.t17.reference_backend import (
    FakeReferenceModelClient,
    ReferenceModelDecision,
)
from skillflow.experiment.t17.reference_harness import ReferenceHarnessFactory
from skillflow.experiment.t17.scenario_registry import (
    load_scenario_measurement_registry,
)
from skillflow.experiment.t17.task_evidence import build_task_success_evidence
from skillflow.instrumentation.errors import UnsupportedStepError
from skillflow.models.scenario import Scenario
from skillflow.store.sqlite_store import SqliteEventStore
from skillflow.validation import validate_yaml_document


def _reference_runner(empty_roots: frozenset[str] = frozenset()) -> ScenarioRunner:
    scripts, decisions = t12_fixture_registry()
    client = FakeReferenceModelClient(
        {
            root: ReferenceModelDecision(
                selected_action_ids=(
                    () if root in empty_roots else tuple(item.action_id for item in script.actions)
                ),
                output_text=script.output.decode(),
                output_mime_type=script.output_mime_type,
            )
            for root, script in scripts.items()
        }
    )
    return ScenarioRunner(
        scripts,
        decisions,
        harness_factory=ReferenceHarnessFactory(client),
    )


def test_reference_harness_runs_b0_through_the_instrumented_runtime(tmp_path: Path) -> None:
    # Given: a Fake model selecting every preregistered B0 action.
    runner = _reference_runner()

    # When: the existing ScenarioRunner executes B0 with the Reference Harness.
    result = runner.run(
        Path("scenarios/benign/b0_legal_summary.yaml"),
        tmp_path / "reference-b0",
        "t17-reference-b0",
    )

    # Then: task, Grant, Effect and Receipt flow through the same core runtime.
    assert result.risk_report.task_success is True
    assert result.risk_report.uea.uea_count == 0
    assert len(result.receipts) == 1

    registry = load_scenario_measurement_registry(
        Path("experiments/t17/scenario_measurements.yaml")
    )
    specification = next(item for item in registry.scenarios if item.scenario_id == "B0")
    with SqliteEventStore(result.database_path) as store:
        task_evidence = build_task_success_evidence(result, specification, store)
        snapshot = build_reference_observations(
            ReferenceObservationRequest(
                store=store,
                run_id=result.run_id,
                receipts=result.receipts,
                task_success_evidence=task_evidence,
                required_hooks=frozenset(
                    {
                        HookName.AUTHORIZATION,
                        HookName.DECISION_BASIS,
                        HookName.PROVENANCE,
                        HookName.TASK_SUCCESS,
                    }
                ),
            )
        )

    assert {item.status for item in snapshot.hooks} <= {
        MeasurementStatus.MEASURED,
        MeasurementStatus.NOT_APPLICABLE,
    }
    assert len(snapshot.authorizations) == 1
    assert snapshot.decisions[0].decision_basis_artifact_ids
    assert snapshot.provenance
    assert snapshot.effects[0].receipt_id == result.receipts[0].receipt_id
    assert snapshot.task_success is not None
    assert snapshot.task_success.task_success is True


def test_reference_observation_rejects_executed_effect_without_receipt(tmp_path: Path) -> None:
    # Given: a valid Reference Harness Run whose trusted Receipt set is withheld.
    result = _reference_runner().run(
        Path("scenarios/benign/b0_legal_summary.yaml"),
        tmp_path / "reference-b0-missing-receipt",
        "t17-reference-b0-missing-receipt",
    )

    # When/Then: the Observation builder refuses to bless the executed Effect.
    with (
        SqliteEventStore(result.database_path) as store,
        pytest.raises(ObservationBindingError),
    ):
        build_reference_observations(
            ReferenceObservationRequest(
                store=store,
                run_id=result.run_id,
                receipts=(),
                task_success_evidence=None,
                required_hooks=frozenset({HookName.AUTHORIZATION}),
            )
        )


def test_required_task_hook_without_evidence_is_not_available(tmp_path: Path) -> None:
    # Given: a valid Run but no deterministic TaskSuccessEvidence supplied.
    result = _reference_runner().run(
        Path("scenarios/benign/b0_legal_summary.yaml"),
        tmp_path / "reference-b0-no-task-evidence",
        "t17-reference-b0-no-task-evidence",
    )

    # When: task_success is required in the Hook manifest.
    with SqliteEventStore(result.database_path) as store:
        snapshot = build_reference_observations(
            ReferenceObservationRequest(
                store=store,
                run_id=result.run_id,
                receipts=result.receipts,
                task_success_evidence=None,
                required_hooks=frozenset({HookName.TASK_SUCCESS}),
            )
        )

    # Then: it is explicitly unavailable rather than self-reported as measured.
    task_hook = next(item for item in snapshot.hooks if item.hook is HookName.TASK_SUCCESS)
    assert task_hook.status is MeasurementStatus.NOT_AVAILABLE


def test_reference_harness_allows_no_effect_without_weakening_artifact_oracle(
    tmp_path: Path,
) -> None:
    scripts, decisions = t12_fixture_registry()
    client = FakeReferenceModelClient(
        {
            root: ReferenceModelDecision(
                selected_action_ids=(
                    ()
                    if root == "fixture://t12/context-consumer"
                    else tuple(item.action_id for item in script.actions)
                ),
                output_text=script.output.decode(),
                output_mime_type=script.output_mime_type,
            )
            for root, script in scripts.items()
        }
    )
    runner = ScenarioRunner(
        scripts,
        decisions,
        harness_factory=ReferenceHarnessFactory(client),
    )
    scenario_path = Path("scenarios/attacks/c1_context_composition.yaml")
    scenario = validate_yaml_document(scenario_path, Scenario)
    run_root = tmp_path / "reference-c1-no-effect"

    result = runner.run_configured(
        ScenarioRunRequest(
            scenario_path=scenario_path,
            scenario=scenario,
            run_id="run-reference-c1-no-effect",
            id_seed="t17-reference-c1-no-effect",
            layout=ScenarioRunLayout(
                run_root=run_root,
                experiment_root=run_root,
                database_path=run_root / "state.sqlite",
                workspace_root=run_root / "workspace",
                security_graph_path=run_root / "graph.json",
                risk_report_path=run_root / "run-report.json",
            ),
            report_metadata=RunReportMetadata(backend="reference_harness"),
        )
    )

    assert result.receipts == ()
    assert result.risk_report.task_success is False
    assert result.risk_report.effects == ()


def test_reference_harness_reports_required_tool_no_call_as_typed_failure(
    tmp_path: Path,
) -> None:
    runner = _reference_runner(
        frozenset(
            {
                "fixture://t12/memory-skill-b-offset1",
                "fixture://t12/memory-skill-b-offset3",
            }
        )
    )
    scenario_path = Path("scenarios/benign/m2_revoked_memory_control.yaml")
    scenario = validate_yaml_document(scenario_path, Scenario)
    run_root = tmp_path / "reference-m2-no-call"

    with pytest.raises(
        UnsupportedStepError,
        match="required input missing: m2-memory-1",
    ):
        runner.run_configured(
            ScenarioRunRequest(
                scenario_path=scenario_path,
                scenario=scenario,
                run_id="run-reference-m2-no-call",
                id_seed="t17-reference-m2-no-call",
                layout=ScenarioRunLayout(
                    run_root=run_root,
                    experiment_root=run_root,
                    database_path=run_root / "state.sqlite",
                    workspace_root=run_root / "workspace",
                    security_graph_path=run_root / "graph.json",
                    risk_report_path=run_root / "run-report.json",
                ),
                report_metadata=RunReportMetadata(backend="reference_harness"),
            )
        )
