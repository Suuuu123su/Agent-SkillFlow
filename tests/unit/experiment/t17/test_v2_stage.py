"""第二版整阶段必须逐个保留调度终态与可复算证据。"""

from pathlib import Path

import pytest

from skillflow.experiment.t17.live_matrix import T17LiveStage
from skillflow.experiment.t17.reference_backend import ReferenceModelDecision, ReferenceModelRequest
from skillflow.experiment.t17.v2.configuration import build_configuration, write_configuration
from skillflow.experiment.t17.v2.matrix import build_matrix
from skillflow.experiment.t17.v2.stage import StageSetup, run_stage


class ChoiceClient:
    def __init__(self, all_actions: bool) -> None:
        self.all_actions = all_actions

    def decide(self, request: ReferenceModelRequest) -> ReferenceModelDecision:
        return ReferenceModelDecision(
            selected_action_ids=request.allowed_action_ids if self.all_actions else (),
            output_text=request.expected_output_text,
        )


@pytest.mark.parametrize("all_actions", [True, False])
def test_complete_fake_canary_has_24_core_18_replay_terminals(
    t17_cli_root: Path, all_actions: bool
) -> None:
    root = Path.cwd()
    target = t17_cli_root / ("all" if all_actions else "none")
    config, bundles = build_configuration(root, target / "config")
    write_configuration(root, target / "config", config, bundles)
    matrix = build_matrix(root, config, T17LiveStage.CANARY)
    result = run_stage(
        StageSetup(
            root, target / "attempt", config, matrix, "fake_reference", ChoiceClient(all_actions)
        )
    )
    assert len(result.cores) == 24
    assert len(result.replays) == 18
    assert result.gate.passed
    assert result.gate.infrastructure_invalid == 0
    assert result.gate.receipt_coverage == 1.0
    assert result.gate.binding_coverage == 1.0
    assert result.gate.usage_complete
    assert result.gate.metric_statuses
    assert set(result.gate.metric_statuses.values()) <= {"measured", "not_applicable"}
    assert all(t.status == "completed" for t in result.cores)
    assert all(t.status in {"completed", "not_applicable"} for t in result.replays)
    assert all(
        t.proof is None or t.proof.source.run_id == t.source_core_run_id for t in result.replays
    )
    assert (target / "attempt" / "raw-manifest.json").exists()
    assert sum(c.usage.api_calls for c in result.cores) == 0
    if all_actions:
        assert (
            sum(c.data.proof.report.uea.uea_count for c in result.cores if c.data is not None) == 8
        )
    else:
        assert any(
            r.status == "not_applicable" and r.reason == "target_not_produced"
            for r in result.replays
        )
        assert all(r.proof is None or r.proof.ci == 0 for r in result.replays)
