from pathlib import Path

import pytest

from skillflow.analysis.facts import RunReportMetadata
from skillflow.benchmark.runner import ScenarioRunLayout, ScenarioRunner, ScenarioRunRequest
from skillflow.defense.rx import TaskConstraints, TaskPermission, TreatmentName
from skillflow.experiment.t17.v2.fake_client import V2FakeClient
from skillflow.experiment.t17.v2.portable import capture_core, recompute_core
from skillflow.experiment.t18.catalog import build_catalog
from skillflow.experiment.t19.runtime import RxHarnessFactory

ROOT = Path(__file__).resolve().parents[3]
CONDITIONS = (
    "c1-attack",
    "c1-neutral",
    "c2-attack",
    "c2-neutral",
    "m2-attack",
    "m2-neutral",
    "a1-attack",
    "a1-neutral",
    "b0-benign-control",
    "n0-benign-control",
    "g0-benign-control",
    "a2-benign-control",
    "b1-attack",
    "s1-attack",
    "l1-attack",
)


@pytest.mark.parametrize("condition", CONDITIONS)
@pytest.mark.parametrize("treatment", ["Monitor", "Grant-only", "All", "Evidence", "Coarse"])
def test_rx_existing_runtime_preserves_authorization_and_receipts(
    condition: str,
    treatment: TreatmentName,
    tmp_path: Path,
) -> None:
    skill = next(
        s
        for s in build_catalog(ROOT, include_held_out=False).skills
        if s.skill_variant_id == condition
    )
    # Adapter regression only: the formal task contract must be authored independently.
    constraints = TaskConstraints(
        contract_id="adapter-test",
        permissions=tuple(
            TaskPermission(
                actor_id=n.actor_id,
                session_ids=(n.session_id,),
                effect=n.effect,
                evidence_id="fixture-user-task",
            )
            for n in skill.task_plan.nodes
        ),
    )
    factory = RxHarnessFactory(constraints, treatment, V2FakeClient())
    metadata = RunReportMetadata(experiment_id="t19-adapter-test", backend="reference_harness")
    output = tmp_path / "run"
    result = ScenarioRunner(
        skill.bundle.scripts,
        skill.bundle.decisions,
        factory,
        execution_policy=factory.execution_policy,
    ).run_configured(
        ScenarioRunRequest(
            ROOT / skill.scenario_path,
            skill.scenario,
            "rx-test",
            "rx-test",
            ScenarioRunLayout(
                output,
                output,
                output / "state.sqlite",
                output / "workspace",
                output / "graph.json",
                output / "risk.json",
            ),
            metadata,
        )
    )
    core = capture_core(result, skill.scenario, skill.task_contract, metadata)
    assert recompute_core(core) == core.proof
    traces = factory.providers["rx-test"].traces
    assert all(t.authorized_before == t.authorized_after for t in traces)
    assert all(not t.executed_after or t.executed_before for t in traces)
    if treatment != "Monitor":
        assert all(t.authorized_after for t in traces if t.executed_after)
    if condition in {"g0-benign-control", "a2-benign-control"}:
        assert core.proof.task.task_success
        assert result.receipts
    if condition == "c2-attack":
        assert any(
            s.channel == "tool" and not s.instruction_authority
            for t in traces
            for s in t.evidence.sources
        )
    if condition == "m2-neutral":
        assert core.proof.task.task_success
    if treatment == "All" and condition == "c2-attack":
        assert factory.backends["rx-test"].recoveries
        assert all(
            r.additional_model_decisions == 1 for r in factory.backends["rx-test"].recoveries
        )
