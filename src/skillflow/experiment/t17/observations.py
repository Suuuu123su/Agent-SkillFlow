"""从受信 EventStore 与 Receipt 机械投影 T17 Hook 证据。"""

from skillflow.experiment.t17.observation_hooks import (
    HookEvidenceBundle,
    hook_capabilities,
)
from skillflow.experiment.t17.observation_models import (
    AuthorizationObservation,
    DecisionBasisObservation,
    EffectObservation,
    InfluenceObservation,
    ObservationBindingError,
    ProvenanceObservation,
    ReferenceObservationRequest,
    ReferenceObservationSnapshot,
    RevocationObservation,
)
from skillflow.models.replay_reports import ReplayRiskReport
from skillflow.store.event_store import RevocationTargetKind

__all__ = [
    "AuthorizationObservation",
    "DecisionBasisObservation",
    "EffectObservation",
    "InfluenceObservation",
    "ObservationBindingError",
    "ProvenanceObservation",
    "ReferenceObservationRequest",
    "ReferenceObservationSnapshot",
    "RevocationObservation",
    "build_influence_observations",
    "build_reference_observations",
]


def build_reference_observations(
    request: ReferenceObservationRequest,
) -> ReferenceObservationSnapshot:
    """从追加事实生成快照，不读取模型自报来源或授权。"""
    events = request.store.iter_run_events(request.run_id)
    events_by_id = {item.event_id: item for item in events}
    receipts = {item.receipt_id: item for item in request.receipts}
    effects = {item.decision_id: item for item in request.store.iter_run_effects(request.run_id)}
    decision_ids = tuple(
        dict.fromkeys(item.decision_id for item in events if item.decision_id is not None)
    )
    decisions = []
    effect_observations = []
    for decision_id in decision_ids:
        decision = request.store.get_decision(decision_id)
        if decision is None:
            raise ObservationBindingError(decision_id, "decision_missing")
        source_event = events_by_id.get(decision.request_event_id)
        if source_event is None or source_event.requested_effect is None:
            raise ObservationBindingError(decision_id, "request_event_missing")
        effect = effects.get(decision_id)
        receipt_id = None if effect is None else effect.tool_receipt_id
        if decision.executed and (effect is None or receipt_id not in receipts):
            raise ObservationBindingError(decision_id, "executed_effect_receipt_missing")
        decisions.append(
            DecisionBasisObservation(
                decision_id=decision.decision_id,
                request_event_id=decision.request_event_id,
                enforcement_mode=decision.enforcement_mode,
                baseline_result=decision.baseline_result,
                policy_result=decision.policy_result,
                authorized=decision.authorized,
                executed=decision.executed,
                decision_basis_artifact_ids=decision.decision_basis_artifact_ids,
                matched_grant_ids=decision.matched_grant_ids,
                reason_codes=decision.reason_codes,
            )
        )
        effect_observations.append(
            EffectObservation(
                request_event_id=decision.request_event_id,
                decision_id=decision.decision_id,
                requested_effect=source_event.requested_effect,
                executed=decision.executed,
                effect_id=None if effect is None else effect.effect_id,
                receipt_id=receipt_id,
            )
        )
    revocations = request.store.iter_run_revocations(request.run_id)
    revocations_by_grant = {
        item.target_id: item
        for item in revocations
        if item.target_kind is RevocationTargetKind.GRANT
    }
    grant_events = {
        str(item.metadata["grant_id"]): item.event_id
        for item in events
        if "grant_id" in item.metadata
    }
    authorizations = []
    for grant in request.store.iter_run_grants(request.run_id):
        event_id = grant_events.get(grant.grant_id)
        if event_id is None:
            raise ObservationBindingError(grant.grant_id, "grant_event_missing")
        revocation = revocations_by_grant.get(grant.grant_id)
        authorizations.append(
            AuthorizationObservation(
                grant=grant,
                grant_event_id=event_id,
                revoked=revocation is not None,
                revoke_event_id=None if revocation is None else revocation.event_id,
            )
        )
    artifact_ids = tuple(
        dict.fromkeys(artifact_id for event in events for artifact_id in event.output_artifact_ids)
    )
    provenance = []
    for artifact_id in artifact_ids:
        artifact = request.store.get_artifact(artifact_id)
        if artifact is None:
            raise ObservationBindingError(artifact_id, "artifact_missing")
        provenance.append(
            ProvenanceObservation(
                artifact_id=artifact.artifact_id,
                created_by_event_id=artifact.created_by_event_id,
                created_session_id=artifact.observed_label.created_session_id,
                parent_artifact_ids=artifact.observed_label.parent_artifact_ids,
                origins=artifact.observed_label.origins,
                revoked_origins=artifact.observed_label.revoked_origins,
                trust=artifact.observed_label.trust,
            )
        )
    task = request.task_success_evidence
    if task is not None and task.run_id != request.run_id:
        raise ObservationBindingError(task.run_id, "task_evidence_run_mismatch")
    revocation_observations = tuple(
        RevocationObservation(
            revocation_id=item.revocation_id,
            target_kind=item.target_kind,
            target_id=item.target_id,
            event_id=item.event_id,
            timestamp=item.timestamp,
        )
        for item in revocations
    )
    authorization_observations = tuple(authorizations)
    decision_observations = tuple(decisions)
    provenance_observations = tuple(provenance)
    effects_observed = tuple(effect_observations)
    return ReferenceObservationSnapshot(
        run_id=request.run_id,
        hooks=hook_capabilities(
            request.required_hooks,
            HookEvidenceBundle(
                authorization_observations,
                decision_observations,
                provenance_observations,
                revocation_observations,
                request.influences,
                task,
            ),
        ),
        authorizations=authorization_observations,
        decisions=decision_observations,
        provenance=provenance_observations,
        effects=effects_observed,
        revocations=revocation_observations,
        influences=request.influences,
        task_success=task,
    )


def build_influence_observations(
    reports: tuple[ReplayRiskReport, ...],
) -> tuple[InfluenceObservation, ...]:
    """把每个完整 Replay pair 投影为可审计 Influence Hook 证据。"""
    return tuple(
        InfluenceObservation(
            replay_id=item.replay_id,
            ci=item.ci,
            source_artifact_id=item.intervention_artifact_id,
            target_effect_ids=tuple(
                edge.target_effect_id for edge in item.confirmed_influence_edges
            ),
            evidence_ids=(
                item.replay_id,
                item.original_run_id,
                item.neutral_run_id,
                *item.original_receipt_ids,
                *item.neutral_receipt_ids,
            ),
        )
        for item in reports
    )
