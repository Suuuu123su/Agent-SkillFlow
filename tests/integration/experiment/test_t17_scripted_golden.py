from pathlib import Path

from skillflow.experiment.t17.scripted_golden import ScriptedGoldenStatus
from skillflow.experiment.t17.scripted_runner import (
    T17ScriptedRunRequest,
    execute_t17_scripted,
)


def test_t17_scripted_summary_reproduces_the_frozen_mvp_golden(tmp_path: Path) -> None:
    # Given: a new output root and independent static Matrix/registry/Golden inputs.
    output = tmp_path / "t17-scripted"
    summary_path = tmp_path / "summary.json"

    # When: T17-D runs the complete chain and rebuilds checked reports/observations.
    outcome = execute_t17_scripted(
        T17ScriptedRunRequest(
            matrix_path=Path("scenarios/matrix/mvp.yaml"),
            registry_path=Path("experiments/t17/scenario_measurements.yaml"),
            golden_path=Path("experiments/t17/scripted_golden.yaml"),
            output_root=output,
            summary_output=summary_path,
        )
    )
    summary = outcome.summary

    # Then: every core/replay/determinism, coverage and advanced metric matches.
    assert summary.status is ScriptedGoldenStatus.PASSED
    assert (summary.observed_core_runs, summary.observed_replay_pairs) == (24, 18)
    assert summary.task_success_rate.numerator == 20
    assert summary.safe_task_success_rate.numerator == 11
    assert summary.uea_count == 8
    assert summary.hiaa_c1 == 1.0
    assert summary.hiaa_c2 == 1.0
    assert (summary.alr.numerator, summary.alr.denominator) == (1, 2)
    assert (summary.rir_1.numerator, summary.rir_3.numerator) == (1, 1)
    assert summary.causal_impact.zero == 9
    assert summary.causal_impact.positive == 9
    assert summary.task_success_evidence_coverage.value == 1.0
    assert summary.receipt_coverage.value == 1.0
    assert summary.hook_coverage.value == 1.0
    assert summary.provenance.precision.value == 1.0
