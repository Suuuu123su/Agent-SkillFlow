"""基于真实 Tool Receipt 的 T10 配对差异分析。"""

from dataclasses import dataclass

from skillflow.analysis.counterfactual import compute_scripted_ci
from skillflow.analysis.effect_selection import (
    EffectSelectionFacts,
    select_receipted_effects,
)
from skillflow.benchmark.replay_models import (
    ReplayBranchResult,
    ReplayControlEvidence,
    ReplayInterventionEvidence,
    ReplayPairManifest,
    ReplaySourceState,
)
from skillflow.models.effects import EffectRecord
from skillflow.models.reports import ConfirmedInfluenceEdge, ReplayRiskReport
from skillflow.models.scenario_parts import EffectSelector


@dataclass(frozen=True, slots=True)
class ReplayAnalysisSetup:
    """生成报告与证据清单所需的完整配对事实。"""

    replay_id: str
    target_alias: str
    source: ReplaySourceState
    original: ReplayBranchResult
    neutral: ReplayBranchResult
    selector: EffectSelector
    controls: ReplayControlEvidence


@dataclass(frozen=True, slots=True)
class ReplayAnalysisResult:
    """Schema 化风险报告与分支控制清单。"""

    report: ReplayRiskReport
    manifest: ReplayPairManifest


def analyze_replay_pair(setup: ReplayAnalysisSetup) -> ReplayAnalysisResult:
    """只把 selector 命中的已执行 Effect 与实际 Receipt 纳入 CI。"""
    original_effects = _receipted_effects(setup.original, setup.selector)
    neutral_effects = _receipted_effects(setup.neutral, setup.selector)
    original_ids = tuple(effect.effect_id for effect in original_effects)
    neutral_ids = tuple(effect.effect_id for effect in neutral_effects)
    observed_ids = tuple(dict.fromkeys((*original_ids, *neutral_ids)))
    removed_ids = tuple(item for item in original_ids if item not in neutral_ids)
    added_ids = tuple(item for item in neutral_ids if item not in original_ids)
    ci = compute_scripted_ci(bool(original_ids), bool(neutral_ids))
    edge_targets = removed_ids if ci == 1 else added_ids if ci == -1 else ()
    report = ReplayRiskReport(
        schema_version="0.1",
        report_scope="replay",
        replay_id=setup.replay_id,
        original_run_id=setup.original.run_id,
        neutral_run_id=setup.neutral.run_id,
        intervention_artifact_id=setup.source.source_artifact_id,
        original_intervention_artifact_id=(setup.original.intervention.derived.artifact_id),
        neutral_intervention_artifact_id=setup.neutral.intervention.derived.artifact_id,
        observed_effect_ids=observed_ids,
        original_effect_ids=original_ids,
        neutral_effect_ids=neutral_ids,
        removed_effect_ids=removed_ids,
        added_effect_ids=added_ids,
        y_original=bool(original_ids),
        y_neutral=bool(neutral_ids),
        ci=ci,
        confirmed_influence_edges=tuple(
            ConfirmedInfluenceEdge(
                source_artifact_id=setup.source.source_artifact_id,
                target_effect_id=effect_id,
            )
            for effect_id in edge_targets
        ),
    )
    return ReplayAnalysisResult(report, _build_manifest(setup, report))


def _receipted_effects(
    branch: ReplayBranchResult,
    selector: EffectSelector,
) -> tuple[EffectRecord, ...]:
    selected = select_receipted_effects(
        EffectSelectionFacts(branch.effects, branch.receipts, selector)
    )
    return tuple(item.effect for item in selected)


def _build_manifest(
    setup: ReplayAnalysisSetup,
    report: ReplayRiskReport,
) -> ReplayPairManifest:
    checkpoint = setup.source.checkpoint
    return ReplayPairManifest(
        replay_id=setup.replay_id,
        target_alias=setup.target_alias,
        checkpoint_id=checkpoint.checkpoint_id,
        checkpoint_prefix_hash=checkpoint.prefix_hash,
        checkpoint_state_hash=checkpoint.state_hash,
        original_run_id=setup.original.run_id,
        neutral_run_id=setup.neutral.run_id,
        original_restore_state_hash=setup.original.restore_state_hash,
        neutral_restore_state_hash=setup.neutral.restore_state_hash,
        original_prefix_hash=setup.original.prefix_hash,
        neutral_prefix_hash=setup.neutral.prefix_hash,
        controls=setup.controls,
        original_intervention=_intervention_evidence(setup.original),
        neutral_intervention=_intervention_evidence(setup.neutral),
        original_effect_ids=report.original_effect_ids,
        neutral_effect_ids=report.neutral_effect_ids,
        removed_effect_ids=report.removed_effect_ids,
        added_effect_ids=report.added_effect_ids,
    )


def _intervention_evidence(branch: ReplayBranchResult) -> ReplayInterventionEvidence:
    result = branch.intervention
    derived = result.derived
    return ReplayInterventionEvidence(
        mode=result.mode.value,
        source_artifact_id=result.original.artifact_id,
        derived_artifact_id=derived.artifact_id,
        artifact_type=derived.artifact_type,
        mime_type=derived.mime_type,
        content_hash=derived.content_hash,
        content_length=derived.content_length,
        schema_preserved=result.schema_preserved,
    )
