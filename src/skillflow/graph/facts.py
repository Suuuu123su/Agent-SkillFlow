"""从 EventStore 装载单个 Run 的强类型图事实。"""

from dataclasses import dataclass

from skillflow.graph.errors import GraphBuildError
from skillflow.models.effects import EffectRecord
from skillflow.models.events import DecisionRecord, SecurityEvent
from skillflow.models.provenance import Artifact
from skillflow.store.event_store import EventStore


@dataclass(frozen=True, slots=True)
class RunGraphFacts:
    """单个 Run 内完成构图所需的持久事实快照。"""

    run_id: str
    events: tuple[SecurityEvent, ...]
    artifacts: tuple[Artifact, ...]
    decisions: tuple[DecisionRecord, ...]
    effects: tuple[EffectRecord, ...]


def load_run_graph_facts(store: EventStore, run_id: str) -> RunGraphFacts:
    """只经 EventStore 公共合同读取构图所需事实。"""
    events = store.iter_run_events(run_id)
    artifact_ids = tuple(
        dict.fromkeys(
            artifact_id
            for event in events
            for artifact_id in (*event.input_artifact_ids, *event.output_artifact_ids)
        )
    )
    artifacts: list[Artifact] = []
    for artifact_id in artifact_ids:
        artifact = store.get_artifact(artifact_id)
        if artifact is None:
            raise GraphBuildError(artifact_id, "Event 引用的 Artifact 不存在")
        artifacts.append(artifact)

    decisions: dict[str, DecisionRecord] = {}
    for event in events:
        if event.decision_id is None or event.decision_id in decisions:
            continue
        decision = store.get_decision(event.decision_id)
        if decision is None:
            raise GraphBuildError(event.event_id, "Event 引用的 DecisionRecord 不存在")
        decisions[decision.decision_id] = decision
    return RunGraphFacts(
        run_id=run_id,
        events=events,
        artifacts=tuple(artifacts),
        decisions=tuple(decisions.values()),
        effects=store.iter_run_effects(run_id),
    )
