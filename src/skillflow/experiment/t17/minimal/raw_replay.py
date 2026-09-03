"""从隔离 Replay 分支的 SQLite/Blob 重新核对 CI 与真实 Receipt。"""

import hashlib
from pathlib import Path

from skillflow.analysis.effect_selection import (
    EffectSelectionFacts,
    effect_matches_selector,
    select_receipted_effects,
)
from skillflow.benchmark.replay_models import ReplayInterventionEvidence, ReplayPairManifest
from skillflow.experiment.t17.minimal.raw_validation import (
    read_model,
    restore_run_receipts,
    verify_run_blobs,
)
from skillflow.experiment.t17.minimal.replay_prefix import verify_replay_prefix
from skillflow.models.effects import EffectRecord
from skillflow.models.enums import Decision
from skillflow.models.matrix import ExperimentVariant
from skillflow.models.reports import ReplayRiskReport
from skillflow.models.scenario import Scenario
from skillflow.models.scenario_parts import EffectSelector
from skillflow.store.event_store import EventStore
from skillflow.store.sqlite_store import SqliteEventStore


def verify_replay(
    root: Path,
    report: ReplayRiskReport,
    variant: ExperimentVariant,
    scenario: Scenario,
) -> None:
    """配对证据必须与两个独立分支事实逐项一致。"""
    manifest = read_model(
        root / "replays" / report.replay_id / "pair-manifest.json", ReplayPairManifest
    )
    index, counterfactual = next(
        (index, item)
        for index, item in enumerate(scenario.counterfactuals, 1)
        if item.target.alias == report.target_alias and item.observe.alias == report.selector_alias
    )
    selector = next(
        item for item in scenario.effect_selectors if item.alias == report.selector_alias
    )
    namespace = hashlib.sha256(variant.variant.encode()).hexdigest()[:8]
    pair = root / "blobs" / "r" / namespace / f"p{index}"
    source_id = report.original_run_id.removesuffix("-original") + "-source"
    verify_replay_prefix(pair, source_id, report.original_run_id, report.neutral_run_id)
    with SqliteEventStore(pair / "s" / "state.sqlite") as source:
        prefix = frozenset(item.effect_id for item in source.iter_run_effects(source_id))
        source_artifact = source.get_artifact(report.intervention_artifact_id)
        if source_artifact is None:
            raise ValueError("minimal_replay_source_artifact_missing")
    original = _branch(
        pair / "o", report.original_run_id, prefix, selector, manifest.original_intervention
    )
    neutral = _branch(
        pair / "n", report.neutral_run_id, prefix, selector, manifest.neutral_intervention
    )
    if (
        original[0] != report.original_effect_ids
        or original[1] != report.original_receipt_ids
        or neutral[0] != report.neutral_effect_ids
        or neutral[1] != report.neutral_receipt_ids
        or original[2] != report.original_baseline_result
        or neutral[2] != report.neutral_baseline_result
        or report.ci != int(bool(original[0])) - int(bool(neutral[0]))
    ):
        raise ValueError("minimal_replay_receipt_recompute_mismatch")
    if (
        manifest.replay_id != report.replay_id
        or manifest.original_run_id != report.original_run_id
        or manifest.neutral_run_id != report.neutral_run_id
        or manifest.target_alias != counterfactual.target.alias
        or manifest.original_effect_ids != report.original_effect_ids
        or manifest.neutral_effect_ids != report.neutral_effect_ids
        or manifest.original_intervention.source_artifact_id != source_artifact.artifact_id
        or manifest.original_intervention.content_hash != source_artifact.content_hash
        or manifest.original_intervention.derived_artifact_id
        != report.original_intervention_artifact_id
        or manifest.neutral_intervention.derived_artifact_id
        != report.neutral_intervention_artifact_id
        or not report.neutralization_preserves_other_inputs
    ):
        raise ValueError("minimal_replay_manifest_binding")


def _branch(
    root: Path,
    run_id: str,
    prefix: frozenset[str],
    selector: EffectSelector,
    intervention: ReplayInterventionEvidence,
) -> tuple[tuple[str, ...], tuple[str, ...], Decision | None]:
    with SqliteEventStore(root / "state.sqlite") as store:
        all_receipts = restore_run_receipts(store, root, run_id)
        verify_run_blobs(store, root, run_id)
        effects = tuple(
            item for item in store.iter_run_effects(run_id) if item.effect_id not in prefix
        )
        effect_ids = {item.effect_id for item in effects}
        receipts = tuple(item for item in all_receipts if item.effect_id in effect_ids)
        selected = select_receipted_effects(EffectSelectionFacts(effects, receipts, selector))
        _verify_intervention(store, intervention)
        return (
            tuple(item.effect.effect_id for item in selected),
            tuple(item.receipt.receipt_id for item in selected),
            _baseline(store, run_id, effects, selector),
        )


def _verify_intervention(store: EventStore, expected: ReplayInterventionEvidence) -> None:
    source = store.get_artifact(expected.source_artifact_id)
    derived = store.get_artifact(expected.derived_artifact_id)
    if source is None or derived is None:
        raise ValueError("minimal_replay_intervention_missing")
    actual = (
        derived.artifact_type,
        derived.mime_type,
        derived.content_length,
        derived.content_hash,
    )
    if actual != (
        expected.artifact_type,
        expected.mime_type,
        expected.content_length,
        expected.content_hash,
    ):
        raise ValueError("minimal_replay_intervention_commitment")
    if (
        source.artifact_id not in derived.observed_label.parent_artifact_ids
        or (source.artifact_type, source.mime_type, source.content_length) != actual[:3]
    ):
        raise ValueError("minimal_replay_intervention_structure")


def _baseline(
    store: EventStore,
    run_id: str,
    effects: tuple[EffectRecord, ...],
    selector: EffectSelector,
) -> Decision | None:
    decisions = tuple(
        decision
        for event in store.iter_run_events(run_id)
        if event.decision_id is not None
        if (decision := store.get_decision(event.decision_id)) is not None
    )
    by_id = {item.decision_id: item for item in decisions}
    for effect in effects:
        if effect_matches_selector(effect, selector) and effect.decision_id in by_id:
            return by_id[effect.decision_id].baseline_result
    return decisions[-1].baseline_result if decisions else None
