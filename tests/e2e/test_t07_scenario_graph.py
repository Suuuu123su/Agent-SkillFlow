from pathlib import Path

from skillflow.benchmark.runner import ScenarioRunner
from skillflow.benchmark.scripted_backend import FixtureScript, ToolScriptAction
from skillflow.graph.models import SecurityGraphExport
from skillflow.graph.security import SecurityGraph
from skillflow.instrumentation.tool_types import ReadFileArgs
from skillflow.models.enums import Decision
from skillflow.models.resources import ResourceRef
from skillflow.store.sqlite_store import SqliteEventStore

SCENARIO = Path(__file__).parents[1] / "fixtures" / "t06" / "authorized_read.yaml"


def make_runner() -> ScenarioRunner:
    return ScenarioRunner(
        scripts={
            "fixture://benign_reader": FixtureScript(
                output=b"fixture completed",
                actions=(
                    ToolScriptAction(
                        action_id="read-report",
                        decision_key="allow-report-read",
                        arguments=ReadFileArgs(
                            resource=ResourceRef("workspace:/documents/report.txt")
                        ),
                    ),
                ),
            )
        },
        decisions={"allow-report-read": Decision.ALLOW},
    )


def test_scenario_runner_exports_sanitized_security_graph(tmp_path: Path) -> None:
    result = make_runner().run(SCENARIO, tmp_path / "run", seed="t07-e2e")

    exported = SecurityGraphExport.model_validate_json(
        result.security_graph_path.read_text(encoding="utf-8")
    )

    text = result.security_graph_path.read_text(encoding="utf-8")
    assert exported.run_id == result.run_id
    assert "T06_SECRET_MARKER" not in text
    assert "fixture completed" not in text


def test_persisted_run_can_rebuild_skill_to_effect_path_after_restart(tmp_path: Path) -> None:
    result = make_runner().run(SCENARIO, tmp_path / "run", seed="t07-restart")
    effect_id = result.receipts[0].effect_id

    with SqliteEventStore(result.database_path) as store:
        graph = SecurityGraph.from_store(store, result.run_id)
        paths = graph.find_skill_to_effect_paths("benign_reader")

    assert any(path.nodes[-1].node_id == effect_id for path in paths)
