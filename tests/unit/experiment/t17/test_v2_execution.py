"""模型没有生成输入时，第二版必须留下完整而非伪造的任务终态。"""

from pathlib import Path

import pytest

from skillflow.analysis.facts import RunReportMetadata
from skillflow.benchmark.replay import ReplayRunner
from skillflow.benchmark.runner import ScenarioRunLayout, ScenarioRunner, ScenarioRunRequest
from skillflow.benchmark.t12_fixtures import t12_fixture_registry
from skillflow.experiment.t17.minimal.configuration import build_minimal_configuration
from skillflow.experiment.t17.minimal.task_evidence import evaluate_normal_task
from skillflow.experiment.t17.reference_backend import (
    ReferenceModelClient,
    ReferenceModelDecision,
    ReferenceModelRequest,
)
from skillflow.experiment.t17.v2.runtime import V2HarnessFactory
from skillflow.instrumentation.errors import UnsupportedStepError
from skillflow.models.enums import EventType
from skillflow.models.scenario import Scenario
from skillflow.store.sqlite_store import SqliteEventStore
from skillflow.validation import validate_yaml_document

M2 = Path("scenarios/attacks/m2_revoked_memory_residual.yaml")


class NoCallClient:
    def decide(self, request: ReferenceModelRequest) -> ReferenceModelDecision:
        return ReferenceModelDecision(
            selected_action_ids=(), output_text=request.expected_output_text
        )


class ReadOnlyClient:
    def decide(self, request: ReferenceModelRequest) -> ReferenceModelDecision:
        return ReferenceModelDecision(
            selected_action_ids=tuple(a for a in request.allowed_action_ids if "read" in a),
            output_text=request.expected_output_text,
        )


@pytest.mark.parametrize("client", [NoCallClient(), ReadOnlyClient()])
def test_missing_input_finishes_all_sessions_without_fake_receipts(
    tmp_path: Path, client: ReferenceModelClient
) -> None:
    scenario = validate_yaml_document(M2, Scenario)
    scripts, decisions = t12_fixture_registry()
    factory = V2HarnessFactory(client)
    output = tmp_path / "core"
    runner = ScenarioRunner(scripts, decisions, factory, execution_policy=factory.execution_policy)
    result = runner.run_configured(
        ScenarioRunRequest(
            scenario_path=M2,
            scenario=scenario,
            run_id="run-v2-missing",
            id_seed="v2-missing",
            layout=ScenarioRunLayout(
                output,
                output,
                output / "state.sqlite",
                output / "workspace",
                output / "graph.json",
                output / "report.json",
            ),
            report_metadata=RunReportMetadata(backend="reference_harness"),
        )
    )
    task = next(t for t in build_minimal_configuration(Path.cwd()).tasks if t.scenario_id == "M2")
    with SqliteEventStore(result.database_path) as store:
        evidence = evaluate_normal_task(result, task, store)
        ended = [
            e.session_id
            for e in store.iter_run_events(result.run_id)
            if e.event_type is EventType.SESSION_END
        ]
    assert ended == ["session-0", "session-1", "session-2", "session-3"]
    assert not evidence.task_success
    assert not evidence.safe_task_success
    assert not evidence.risk_effect_ids
    assert factory.captures[result.run_id].issues
    assert "m2-memory-3" not in result.artifact_ids_by_alias


def test_absent_replay_target_is_typed_and_source_is_preserved(tmp_path: Path) -> None:
    scripts, decisions = t12_fixture_registry()
    factory = V2HarnessFactory(NoCallClient())
    runner = ReplayRunner(
        scripts, decisions, factory, executor_factory=factory.execution_policy.factory
    )
    with pytest.raises(UnsupportedStepError, match="target alias was not produced"):
        runner.run(M2, tmp_path / "replay", "v2-replay")
    assert tuple((tmp_path / "replay").rglob("state.sqlite"))
    assert len(factory.captures) == 1
    assert next(iter(factory.captures.values())).issues
