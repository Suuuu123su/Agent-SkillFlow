"""把现有确定性 Mock Run 投影为 T15 统一观察。"""

from pathlib import Path

from skillflow.benchmark.runner import ScenarioRunner
from skillflow.benchmark.t12_fixtures import t12_fixture_registry
from skillflow.models.scenario import Scenario
from skillflow.pilot.models import (
    PilotAdapterKind,
    PilotEffectEvidence,
    PilotObservation,
    ProvenanceBasis,
)
from skillflow.store.sqlite_store import SqliteEventStore
from skillflow.validation import validate_yaml_document


class MockPilotAdapter:
    """复用 T12 Mock Harness，不复制策略或分析实现。"""

    def run(self, scenario_path: Path, output_root: Path) -> PilotObservation:
        """执行原 Scenario 并提取 selector 对齐的 Receipt Effect。"""
        scripts, decisions = t12_fixture_registry()
        scenario = validate_yaml_document(scenario_path, Scenario)
        output_root.parent.mkdir(parents=True, exist_ok=True)
        result = ScenarioRunner(scripts, decisions).run(
            scenario_path,
            output_root,
            seed=f"t15-mock-{scenario.id.lower()}",
        )
        aliases = frozenset(item.alias for item in scenario.effect_selectors)
        effects = tuple(
            PilotEffectEvidence(
                effect_alias=next(alias for alias in item.selector_aliases if alias in aliases),
                action=item.effect.action,
                receipt_id=item.receipt_id,
                origin_ids=(),
                policy_fact=(
                    f"authorized={str(item.authorized).lower()};policy={item.policy_result.value}"
                ),
            )
            for item in result.risk_report.effects
            if aliases.intersection(item.selector_aliases)
        )
        with SqliteEventStore(result.database_path) as store:
            events = store.iter_run_events(result.run_id)
        observation = PilotObservation(
            adapter=PilotAdapterKind.MOCK,
            scenario_id=scenario.id,
            security_events=events,
            target_effects=effects,
            provenance_recall=result.risk_report.provenance.overall.recall,
            provenance_basis=ProvenanceBasis.GRAPH_WIDE_ARTIFACTS,
        )
        with (output_root / "observation.json").open("x", encoding="utf-8") as stream:
            stream.write(observation.model_dump_json(indent=2) + "\n")
        return observation
