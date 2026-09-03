"""对照源 checkpoint 的持久前缀，验证 identity/neutral 恢复隔离。"""

from pathlib import Path

from skillflow.experiment.t17.minimal.raw_validation import verify_run_blobs
from skillflow.store.event_store import EventStore
from skillflow.store.sqlite_store import SqliteEventStore


def verify_replay_prefix(pair: Path, source_id: str, original_id: str, neutral_id: str) -> None:
    """同一源前缀的 Event/Artifact/Decision/Effect/Grant 必须原样恢复。"""
    with SqliteEventStore(pair / "s" / "state.sqlite") as source:
        verify_run_blobs(source, pair / "s", source_id)
        for branch, identifier in (("o", original_id), ("n", neutral_id)):
            with SqliteEventStore(pair / branch / "state.sqlite") as target:
                _compare_prefix(source, target, source_id, identifier)


def _compare_prefix(source: EventStore, target: EventStore, source_id: str, target_id: str) -> None:
    events = source.iter_run_events(source_id)
    restored = target.iter_run_events(target_id)[: len(events)]
    expected = tuple(item.model_copy(update={"run_id": target_id}) for item in events)
    if restored != expected:
        raise ValueError("minimal_replay_prefix_event_mismatch")
    for event in events:
        for identifier in event.output_artifact_ids:
            if source.get_artifact(identifier) != target.get_artifact(identifier):
                raise ValueError("minimal_replay_prefix_artifact_mismatch")
        if event.decision_id is not None and source.get_decision(
            event.decision_id
        ) != target.get_decision(event.decision_id):
            raise ValueError("minimal_replay_prefix_decision_mismatch")
    for effect in source.iter_run_effects(source_id):
        if target.get_effect(effect.effect_id) != effect:
            raise ValueError("minimal_replay_prefix_effect_mismatch")
    for grant in source.iter_run_grants(source_id):
        if target.get_grant(grant.grant_id) != grant:
            raise ValueError("minimal_replay_prefix_grant_mismatch")
