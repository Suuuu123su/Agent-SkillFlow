from pathlib import Path

from skillflow.models.metrics import MetricStatus, RatioMetric
from skillflow.pilot.models import PilotAdapterKind, PilotObservation, ProvenanceBasis
from skillflow.pilot.orchestrator import run_pilot_pair


class RecordingAdapter:
    def __init__(self, kind: PilotAdapterKind) -> None:
        self.kind = kind
        self.scenario_paths: list[Path] = []

    def run(self, scenario_path: Path, output_root: Path) -> PilotObservation:
        self.scenario_paths.append(scenario_path)
        return PilotObservation(
            adapter=self.kind,
            scenario_id="B0",
            security_events=(),
            target_effects=(),
            provenance_recall=RatioMetric(
                numerator=0,
                denominator=0,
                value=None,
                status=MetricStatus.NOT_APPLICABLE,
            ),
            provenance_basis=ProvenanceBasis.GRAPH_WIDE_ARTIFACTS,
        )


def test_pair_runs_the_exact_same_scenario_path_on_both_adapters() -> None:
    mock = RecordingAdapter(PilotAdapterKind.MOCK)
    openclaw = RecordingAdapter(PilotAdapterKind.OPENCLAW)
    scenario = Path("scenarios/benign/b0_legal_summary.yaml")

    comparison = run_pilot_pair(scenario, Path("unused-output"), mock, openclaw)

    assert mock.scenario_paths == openclaw.scenario_paths == [scenario]
    assert comparison.scenario_id == "B0"
