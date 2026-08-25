from pathlib import Path

from skillflow.models.metrics import MetricStatus
from skillflow.pilot.mock_adapter import MockPilotAdapter
from skillflow.pilot.models import PilotAdapterKind, ProvenanceBasis


def test_mock_adapter_projects_real_b0_run_without_copying_policy(tmp_path: Path) -> None:
    output = tmp_path / "mock"

    observation = MockPilotAdapter().run(
        Path("scenarios/benign/b0_legal_summary.yaml"),
        output,
    )

    assert observation.adapter is PilotAdapterKind.MOCK
    assert observation.scenario_id == "B0"
    assert len(observation.target_effects) == 1
    assert observation.target_effects[0].effect_alias == "report-read"
    assert observation.target_effects[0].receipt_id
    assert observation.target_effects[0].policy_fact == "authorized=true;policy=allow"
    assert observation.provenance_basis is ProvenanceBasis.GRAPH_WIDE_ARTIFACTS
    assert observation.provenance_recall.status is MetricStatus.DEFINED
    assert observation.security_events
    assert (output / "observation.json").is_file()
