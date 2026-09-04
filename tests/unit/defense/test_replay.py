from pathlib import Path

import pytest

from skillflow.analysis.facts import RunReportMetadata
from skillflow.benchmark.runner import ScenarioRunLayout, ScenarioRunner, ScenarioRunRequest
from skillflow.experiment.t17.v2.portable import capture_core
from skillflow.experiment.t18.catalog import build_catalog
from skillflow.experiment.t18.controls import configured_scenario
from skillflow.experiment.t18.matrix import build_matrix
from skillflow.experiment.t18.replay import ReplayBudget, ReplayCoordinator
from skillflow.experiment.t18.runtime import LocalHarnessFactory

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(
    "trial",
    [
        "c1-attack.causal_only.on",
        "c2-attack.causal_only.on",
        "m1-attack.causal_only.on",
        "m2-attack.causal_only.on",
        "a1-attack.causal_only.on",
    ],
)
def test_online_pair_comes_from_actual_checkpoint_and_blocks_before_effect(
    tmp_path: Path, trial: str
) -> None:
    matrix = build_matrix("scripted")
    cell = next(c for c in matrix.cores if c.trial_id == trial)
    skill = next(
        s
        for s in build_catalog(ROOT, include_held_out=False).skills
        if s.skill_variant_id == cell.skill_variant_id
    )
    scenario = configured_scenario(skill, cell)
    factory = LocalHarnessFactory(skill, cell.mode, matrix.domain)
    run_id = "r-" + trial
    coordinator = ReplayCoordinator(
        ROOT, tmp_path, skill, cell, scenario, factory, run_id, ReplayBudget(2)
    )
    factory.replay = coordinator.online
    directory = tmp_path / "core"
    metadata = RunReportMetadata(backend="reference_harness")
    result = ScenarioRunner(
        skill.bundle.scripts,
        skill.bundle.decisions,
        factory,
        execution_policy=factory.execution_policy,
    ).run_configured(
        ScenarioRunRequest(
            ROOT / skill.scenario_path,
            scenario,
            run_id,
            cell.seed,
            ScenarioRunLayout(
                directory,
                directory,
                directory / "state.sqlite",
                directory / "workspace",
                directory / "graph.json",
                directory / "report.json",
            ),
            metadata,
        )
    )
    core = capture_core(result, scenario, skill.task_contract, metadata)
    # The original file reader labels file bodies USER. Frozen evidence rules do
    # not infer an untrusted tool-return path from its benchmark asset label.
    if cell.base_id == "C2":
        assert core.proof.task.risk_effect_ids
        assert not coordinator.records
        assert not any(t.signals.candidate_influence for t in factory.providers[run_id].traces)
    else:
        assert not core.proof.task.risk_effect_ids
        assert coordinator.records
    assert all(
        r.proof.ci == 1 and r.online and r.source_run_id == run_id for r in coordinator.records
    )
    assert all(
        t.causal is None or t.causal.status != "not_available"
        for t in factory.providers[run_id].traces
    )
    for record in coordinator.records:
        assert coordinator.run_pair(record.target_alias, online=True) == record


def test_replay_budget_does_not_expand() -> None:
    budget = ReplayBudget(1)
    assert budget.reserve() == 1
    with pytest.raises(ValueError, match="budget_exhausted"):
        budget.reserve()
