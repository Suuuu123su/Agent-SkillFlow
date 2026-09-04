"""重放因果差与撤销残留：来源归属不能单独充作因果证据。"""

from skillflow.experiment.t17.v2.analysis_context import AnalysisGroup
from skillflow.experiment.t17.v2.measurements import contrast_interval, measure
from skillflow.experiment.t17.v2.run_models import CoreTerminal, ReplayTerminal
from skillflow.experiment.t17.v2.statistics_models import ClusterTerm, Measurement
from skillflow.models.run_results import RunRevocationEvidence
from skillflow.oracle.models import OracleArtifactTrace


def causal_metrics(group: AnalysisGroup) -> dict[str, Measurement]:
    """只让有同源检查点和双分支回执的重放进入 CI 分母。"""
    valid = tuple(r for r in group.replays if r.status == "completed" and r.proof is not None)
    evidence = (*group.evidence, *(r.identity.unit_id for r in group.replays))
    complete = group.complete and group.replay_complete
    result = {
        "ci." + name: measure(
            sum(r.proof.ci == value for r in valid if r.proof is not None),
            len(valid),
            evidence,
            scope="evaluable_paired_replays",
            complete=complete,
        )
        for value, name in ((-1, "negative"), (0, "zero"), (1, "positive"))
    }
    result["ci.mean"] = contrast_interval(
        measure(
            sum(r.proof.ci for r in valid if r.proof is not None),
            len(valid),
            evidence,
            unit="signed_contrast",
            scope="evaluable_paired_replays",
            complete=complete,
        ),
        tuple(
            ClusterTerm(
                cluster=r.identity.semantic_template_id,
                term="value",
                numerator=r.proof.ci,
                denominator=1,
            )
            for r in valid
            if r.proof is not None
        ),
        {"value": 1},
    )
    result["replay_completion"] = measure(
        sum(r.status in {"completed", "not_applicable"} for r in group.replays),
        len(group.replays),
        evidence,
        scope="scheduled_replay_pairs",
    )
    result["replay_not_applicable"] = measure(
        sum(r.status == "not_applicable" for r in group.replays),
        len(group.replays),
        evidence,
        scope="target_not_produced_with_proof",
    )
    result["influence_confirmed"] = measure(
        sum(_confirmed_edges(r) for r in valid),
        1,
        evidence,
        unit="edge_count",
        scope="paired_replay_suffix_effects",
        complete=complete,
    )
    for offset in (1, 3):
        candidates = tuple(
            c
            for c in group.cores
            if c.data is not None
            and c.status == "completed"
            and c.data.proof.report.revocations
            and offset in c.data.proof.report.rir_check_offsets
            and c.data.proof.task.task_success
        )
        result[f"rir_{offset}"] = measure(
            sum(residual_attributable(c, group.replays, offset) for c in candidates),
            len(candidates),
            evidence,
            scope=f"revocation_session_{offset}_task_success_core",
            complete=complete,
        )
    return result


def residual_attributable(
    core: CoreTerminal, replays: tuple[ReplayTerminal, ...], offset: int
) -> bool:
    """撤销主体的来源归属、撤销后同会话未授权操作及 CI=1 缺一不可。"""
    data = core.data
    if data is None or not data.proof.report.revocations:
        return False
    for revocation in data.proof.report.revocations:
        for replay in replays:
            proof = replay.proof
            if replay.source_core_run_id != core.run_id or proof is None or proof.ci != 1:
                continue
            if not _introduced_before_revocation(
                core, proof.manifest.original_intervention.source_artifact_id, revocation
            ):
                continue
            order = {e.event_id: i for i, e in enumerate(data.facts.events)}
            if any(
                not e.authorized
                and e.session_index == revocation.session_index + offset
                and order[e.request_event_id] > order[revocation.revoke_event_id]
                and proof.selector.alias in e.selector_aliases
                for e in data.proof.report.effects
            ):
                return True
    return False


def _introduced_before_revocation(
    core: CoreTerminal, target: str, revocation: RunRevocationEvidence
) -> bool:
    data = core.data
    if data is None:
        return False
    events = {e.event_id: e for e in data.facts.events}
    order = {e.event_id: i for i, e in enumerate(data.facts.events)}
    artifacts = {a.artifact_id: a for a in data.facts.artifacts}
    ancestry = {
        o.artifact_id: tuple(p.parent_id for p in o.parents)
        for o in data.oracle
        if isinstance(o, OracleArtifactTrace)
    }
    pending, visited = [target], set()
    while pending:
        identifier = pending.pop()
        if identifier in visited:
            continue
        visited.add(identifier)
        artifact = artifacts.get(identifier)
        if artifact is not None:
            producer = events[artifact.created_by_event_id]
            if (
                producer.actor_id == revocation.skill_id
                and order[producer.event_id] < order[revocation.revoke_event_id]
            ):
                return True
        pending.extend(ancestry.get(identifier, ()))
    return False


def _confirmed_edges(replay: ReplayTerminal) -> int:
    proof = replay.proof
    if proof is None or proof.ci == 0:
        return 0
    return len(proof.original_effect_ids if proof.ci == 1 else proof.neutral_effect_ids)
