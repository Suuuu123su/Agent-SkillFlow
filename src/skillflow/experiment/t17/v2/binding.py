"""结构化记录的身份、任务、来源、回执和回放绑定，失败则拒绝发布。"""

from skillflow.experiment.t17.v2.canonical import model_digest
from skillflow.experiment.t17.v2.config_models import V2Configuration
from skillflow.experiment.t17.v2.configuration import canonical_digest
from skillflow.experiment.t17.v2.portable import recompute_core
from skillflow.experiment.t17.v2.portable_models import PortableRun
from skillflow.experiment.t17.v2.replay_proof import build_replay_proof
from skillflow.experiment.t17.v2.run_models import CoreTerminal, ReplayTerminal
from skillflow.models.enums import EventType


def validate_core_binding(config: V2Configuration, core: CoreTerminal) -> None:
    """连同失败单元一起验证身份；完成单元还须逐项复算相等。"""
    CoreTerminal.model_validate(core.model_dump())
    identity = core.identity
    entry = next(
        (v for v in config.catalog.variants if v.skill_variant_id == identity.skill_variant_id),
        None,
    )
    condition = next(
        (
            c
            for c in config.catalog.conditions
            if c.configuration.variant == identity.source_variant
        ),
        None,
    )
    if (
        entry is None
        or condition is None
        or condition.skill_variant_id != identity.skill_variant_id
    ):
        raise ValueError("v2_core_identity_catalog_binding")
    task = next(t for t in config.tasks if t.scenario_path == entry.scenario_path)
    if (
        identity.unit_id != identity.trial_id
        or identity.protocol_id != config.protocol_id
        or identity.skill_content_sha256 != entry.skill_content_sha256
        or identity.manifest_sha256 != entry.manifest_sha256
        or identity.task_contract_id != entry.task_contract_id
        or identity.task_contract_sha256 != model_digest(task)
        or identity.semantic_template_id not in {t.template_id for t in config.templates}
        or identity.repeat_index > config.repeats
    ):
        raise ValueError("v2_core_identity_hash_binding")
    data = core.data
    if data is None:
        return
    if (
        data.task_contract != task
        or data.claim_bindings != config.claim_bindings[entry.skill_variant_id]
    ):
        raise ValueError("v2_core_frozen_contract_binding")
    if (
        data.metadata.variant != identity.condition_id
        or data.metadata.enforcement_mode != identity.enforcement_mode
    ):
        raise ValueError("v2_core_metadata_condition_binding")
    if data.proof != recompute_core(data):
        raise ValueError("v2_core_recomputed_proof_mismatch")
    sessions = tuple(s.id for s in data.analysis_definition.sessions)
    ended = tuple(e.session_id for e in data.facts.events if e.event_type is EventType.SESSION_END)
    if ended != sessions:
        raise ValueError("v2_core_session_completion_binding")
    _validate_decisions(core)


def _validate_decisions(core: CoreTerminal) -> None:
    if core.data is None:
        return
    invokes = {
        e.call_id: e for e in core.data.facts.events if e.event_type is EventType.SKILL_INVOKE
    }
    for decision in core.decisions:
        event = invokes.get(decision.call_id)
        if (
            event is None
            or decision.run_id != core.run_id
            or event.session_id != decision.session_id
            or not set(decision.selected_action_ids) <= set(decision.allowed_action_ids)
            or len(set(decision.selected_action_ids)) != len(decision.selected_action_ids)
        ):
            raise ValueError("v2_model_decision_runtime_binding")
    if core.identity.domain != "scripted" and set(invokes) != {d.call_id for d in core.decisions}:
        raise ValueError("v2_model_decision_coverage")


def validate_replay_binding(core: CoreTerminal, replay: ReplayTerminal) -> None:
    """缺失目标与两分支都必须指向同一实际核心运行，不接受替代来源。"""
    ReplayTerminal.model_validate(replay.model_dump())
    if (
        replay.identity.trial_id != core.identity.trial_id
        or replay.source_core_run_id != core.run_id
    ):
        raise ValueError("v2_replay_core_identity_binding")
    if replay.status not in {"completed", "not_applicable"}:
        return
    data = core.data
    if core.status != "completed" or data is None:
        raise ValueError("v2_replay_core_unavailable")
    spec = next(
        (
            c
            for c in data.analysis_definition.counterfactuals
            if c.target.alias == replay.target_alias
        ),
        None,
    )
    if spec is None:
        raise ValueError("v2_replay_design_binding")
    if replay.status == "not_applicable":
        target_id = data.artifact_ids_by_alias.get(replay.target_alias)
        empty = replay.reason == "target_empty_no_neutral_form" and any(
            a.artifact_id == target_id
            and a.content_length == 0
            and a.content_hash == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
            for a in data.facts.artifacts
        )
        absent = replay.reason == "target_not_produced" and target_id is None
        if replay.absent_source != data.facts or not (absent or empty):
            raise ValueError("v2_replay_false_absence")
        return
    proof = replay.proof
    if proof is None or proof.manifest.replay_id != replay.identity.unit_id:
        raise ValueError("v2_replay_manifest_identity")
    selector = next(
        s for s in data.analysis_definition.effect_selectors if s.alias == spec.observe.alias
    )
    if (
        proof.selector != selector
        or proof.manifest.original_intervention.source_artifact_id
        != data.artifact_ids_by_alias.get(replay.target_alias)
    ):
        raise ValueError("v2_replay_target_selector_binding")
    validate_source_prefix(data.facts, proof.source)
    if proof != build_replay_proof(
        proof.source, proof.original, proof.neutral, selector, proof.manifest
    ):
        raise ValueError("v2_replay_recomputed_proof_mismatch")


def validate_source_prefix(core: PortableRun, source: PortableRun) -> None:
    """检查点的每个事实都来自实际核心运行的同一完整事件前缀。"""
    if source.run_id != core.run_id or source.events != core.events[: len(source.events)]:
        raise ValueError("v2_replay_source_core_prefix")
    original, prefix = core.model_dump(mode="python"), source.model_dump(mode="python")
    for field in ("artifacts", "decisions", "effects", "grants", "revocations", "receipts"):
        if not {canonical_digest(r) for r in prefix[field]} <= {
            canonical_digest(r) for r in original[field]
        }:
            raise ValueError("v2_replay_source_fact_drift:" + field)
