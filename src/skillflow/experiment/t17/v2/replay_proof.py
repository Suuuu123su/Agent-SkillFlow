"""由原始保存点和两个分支事实复算因果差，不使用场景标签。"""

from typing import Literal

from pydantic import TypeAdapter

from skillflow.analysis.effect_selection import EffectSelectionFacts, select_receipted_effects
from skillflow.benchmark.replay_models import ReplayPairManifest, ReplaySourceState
from skillflow.experiment.t17.v2.fact_store import FactStore
from skillflow.experiment.t17.v2.portable import restore_receipts
from skillflow.experiment.t17.v2.portable_models import PortableRun
from skillflow.experiment.t17.v2.run_models import ReplayProof
from skillflow.instrumentation.tool_receipt import ToolReceiptDraft
from skillflow.models.enums import Decision, EventType
from skillflow.models.scenario_parts import EffectSelector


def source_facts(source: ReplaySourceState) -> PortableRun:
    """直接投影核心任务的检查点，不重新调用模型生成源前缀。"""
    checkpoint = source.checkpoint
    envelopes = checkpoint.store.envelopes
    adapter = TypeAdapter(ToolReceiptDraft)
    return PortableRun(
        run_id=checkpoint.source_run_id,
        events=tuple(e.event for e in envelopes),
        artifacts=tuple(a.artifact for a in checkpoint.store.artifacts),
        decisions=tuple(e.decision for e in envelopes if e.decision is not None),
        effects=tuple(e.effect for e in envelopes if e.effect is not None),
        grants=tuple(e.grant for e in envelopes if e.grant is not None),
        revocations=tuple(e.revocation for e in envelopes if e.revocation is not None),
        receipts=tuple(adapter.validate_json(r.to_bytes()) for r in source.execution.receipts),
    )


def build_replay_proof(
    source: PortableRun,
    original: PortableRun,
    neutral: PortableRun,
    selector: EffectSelector,
    manifest: ReplayPairManifest,
) -> ReplayProof:
    """三份事实和同保存点声明必须一致，来源与分支不允许跨 Run 拼接。"""
    ReplayPairManifest.model_validate(manifest.model_dump())
    if (original.run_id, neutral.run_id) != (manifest.original_run_id, manifest.neutral_run_id):
        raise ValueError("v2_replay_branch_run_binding")
    _validate_prefix(source, original)
    _validate_prefix(source, neutral)
    _validate_intervention(
        source,
        original,
        manifest.original_intervention.derived_artifact_id,
        manifest.original_intervention.source_artifact_id,
    )
    _validate_intervention(
        source,
        neutral,
        manifest.neutral_intervention.derived_artifact_id,
        manifest.neutral_intervention.source_artifact_id,
    )
    original_ids = _effect_ids(source, original, selector)
    neutral_ids = _effect_ids(source, neutral, selector)
    if original_ids != manifest.original_effect_ids or neutral_ids != manifest.neutral_effect_ids:
        raise ValueError("v2_replay_effect_receipt_binding")
    ci: Literal[-1, 0, 1] = (
        1 if original_ids and not neutral_ids else -1 if neutral_ids and not original_ids else 0
    )
    return ReplayProof(
        selector=selector,
        source=source,
        original=original,
        neutral=neutral,
        manifest=manifest,
        y_original=bool(original_ids),
        y_neutral=bool(neutral_ids),
        ci=ci,
        original_effect_ids=original_ids,
        neutral_effect_ids=neutral_ids,
        original_baseline=_baseline(source, original, selector),
        neutral_baseline=_baseline(source, neutral, selector),
        evidence_ids=(
            manifest.replay_id,
            manifest.checkpoint_id,
            source.run_id,
            original.run_id,
            neutral.run_id,
            manifest.original_intervention.source_artifact_id,
            *original_ids,
            *neutral_ids,
        ),
    )


def _validate_prefix(source: PortableRun, branch: PortableRun) -> None:
    FactStore(source)
    FactStore(branch)
    normalized = tuple(
        e.model_copy(update={"run_id": source.run_id}) for e in branch.events[: len(source.events)]
    )
    if normalized != source.events:
        raise ValueError("v2_replay_prefix_drift")
    artifacts = {a.artifact_id: a for a in branch.artifacts}
    if any(artifacts.get(a.artifact_id) != a for a in source.artifacts):
        raise ValueError("v2_replay_prefix_artifact_drift")


def _validate_intervention(
    source: PortableRun, branch: PortableRun, derived: str, target: str
) -> None:
    old = next((a for a in source.artifacts if a.artifact_id == target), None)
    new = next((a for a in branch.artifacts if a.artifact_id == derived), None)
    if old is None or new is None or target not in new.observed_label.parent_artifact_ids:
        raise ValueError("v2_replay_intervention_binding")
    if (old.artifact_type, old.mime_type, old.content_length) != (
        new.artifact_type,
        new.mime_type,
        new.content_length,
    ):
        raise ValueError("v2_replay_intervention_structure")


def _effect_ids(
    source: PortableRun, branch: PortableRun, selector: EffectSelector
) -> tuple[str, ...]:
    receipts = restore_receipts(branch, FactStore(branch))
    prefix = {e.effect_id for e in source.effects}
    effects = tuple(e for e in branch.effects if e.effect_id not in prefix)
    selected = select_receipted_effects(
        EffectSelectionFacts(
            effects, tuple(r for r in receipts if r.effect_id not in prefix), selector
        )
    )
    return tuple(e.effect.effect_id for e in selected)


def _baseline(
    source: PortableRun, branch: PortableRun, selector: EffectSelector
) -> Decision | None:
    requests = set()
    for event in branch.events[len(source.events) :]:
        effect = event.requested_effect
        if event.event_type is not EventType.TOOL_CALL_REQUEST or effect is None:
            continue
        source_matches = (selector.source_pattern is None and effect.source is None) or (
            selector.source_pattern is not None
            and effect.source is not None
            and selector.source_pattern.matches_exact(effect.source)
        )
        if (
            source_matches
            and selector.action is effect.action
            and selector.sink_pattern.matches_exact(effect.sink)
        ):
            requests.add(event.event_id)
    values = {d.baseline_result for d in branch.decisions if d.request_event_id in requests}
    if len(values) > 1:
        raise ValueError("v2_replay_baseline_ambiguous")
    return next(iter(values), None)
