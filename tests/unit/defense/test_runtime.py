from pathlib import Path

import pytest

from skillflow.analysis.facts import RunReportMetadata
from skillflow.benchmark.runner import ScenarioRunLayout, ScenarioRunner, ScenarioRunRequest
from skillflow.experiment.t17.v2.portable import capture_core
from skillflow.experiment.t18.catalog import build_catalog
from skillflow.experiment.t18.controls import configured_scenario
from skillflow.experiment.t18.matrix import build_matrix
from skillflow.experiment.t18.runtime import LocalHarnessFactory

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(
    ("trial", "risk", "success"),
    [
        ("c1-attack.monitor.on", True, True),
        ("c1-attack.tdg_only.on", False, True),
        ("c2-attack.tdg_only.on", False, True),
        ("b1-attack.monitor.on", True, True),
        ("b1-attack.task_alignment_only.on", False, False),
    ],
)
def test_real_runtime_preserves_authorization_and_receipts(
    tmp_path: Path, trial: str, risk: bool, success: bool
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
    root = tmp_path / "core"
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
            "r-" + trial,
            cell.seed,
            ScenarioRunLayout(
                root,
                root,
                root / "state.sqlite",
                root / "workspace",
                root / "graph.json",
                root / "report.json",
            ),
            metadata,
        )
    )
    core = capture_core(result, scenario, skill.task_contract, metadata)
    assert bool(core.proof.task.risk_effect_ids) is risk
    assert core.proof.task.task_success is success
    assert len(core.facts.effects) == len(core.facts.receipts)
    for trace in factory.providers[result.run_id].traces:
        assert trace.base_authorized == trace.final_authorized
    if trial == "b1-attack.monitor.on":
        assert any(d.executed and not d.authorized for d in core.facts.decisions)
