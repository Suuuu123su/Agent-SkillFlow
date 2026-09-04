"""脱敏事实可以在没有原始正文和磁盘数据库时复算。"""

from pathlib import Path

import pytest

from skillflow.analysis.facts import RunReportMetadata
from skillflow.benchmark.runner import ScenarioRunLayout, ScenarioRunner, ScenarioRunRequest
from skillflow.benchmark.t12_fixtures import t12_fixture_registry
from skillflow.experiment.t17.minimal.configuration import build_minimal_configuration
from skillflow.experiment.t17.reference_backend import ReferenceModelDecision, ReferenceModelRequest
from skillflow.experiment.t17.v2.portable import capture_core, recompute_core
from skillflow.experiment.t17.v2.portable_models import PortableCore
from skillflow.experiment.t17.v2.runtime import V2HarnessFactory
from skillflow.models.scenario import Scenario
from skillflow.validation import validate_yaml_document


class AllClient:
    def decide(self, request: ReferenceModelRequest) -> ReferenceModelDecision:
        return ReferenceModelDecision(
            selected_action_ids=request.allowed_action_ids, output_text=request.expected_output_text
        )


def test_portable_facts_recompute_and_reject_cross_run(tmp_path: Path) -> None:
    path = Path("scenarios/attacks/m2_revoked_memory_residual.yaml")
    scenario = validate_yaml_document(path, Scenario)
    scripts, decisions = t12_fixture_registry()
    factory = V2HarnessFactory(AllClient())
    output = tmp_path / "core"
    metadata = RunReportMetadata(backend="reference_harness")
    result = ScenarioRunner(
        scripts, decisions, factory, execution_policy=factory.execution_policy
    ).run_configured(
        ScenarioRunRequest(
            path,
            scenario,
            "run-portable",
            "portable-seed",
            ScenarioRunLayout(
                output,
                output,
                output / "state.sqlite",
                output / "workspace",
                output / "graph.json",
                output / "report.json",
            ),
            metadata,
        )
    )
    task = next(t for t in build_minimal_configuration(Path.cwd()).tasks if t.scenario_id == "M2")
    core = capture_core(result, scenario, task, metadata)
    restored = PortableCore.model_validate_json(core.model_dump_json())
    assert recompute_core(restored) == core.proof
    assert core.proof.task.task_success
    assert len(core.proof.report.unauthorized_effects) == 2
    assert scenario.task.prompt not in core.model_dump_json()
    assert "memory-target!" not in core.model_dump_json()
    changed = core.facts.events[0].model_copy(update={"run_id": "run-other"})
    tampered = core.model_copy(
        update={
            "facts": core.facts.model_copy(update={"events": (changed, *core.facts.events[1:])})
        }
    )
    with pytest.raises(ValueError, match="run_binding"):
        recompute_core(tampered)
