"""从 EventStore 恢复标准 RunResult 所需的决策与撤销事实。"""

from skillflow.analysis.effect_projection import EffectAnalysisEvidence
from skillflow.models.effects import EffectRecord
from skillflow.models.run_results import RunRevocationEvidence
from skillflow.models.scenario import Scenario
from skillflow.store.errors import StoreIntegrityError
from skillflow.store.event_store import EventStore, RevocationTargetKind


def load_effect_analysis_evidence(
    store: EventStore,
    effects: tuple[EffectRecord, ...],
) -> tuple[EffectAnalysisEvidence, ...]:
    """恢复每个 Effect 的 Decision 与依据 Artifact。"""
    values: list[EffectAnalysisEvidence] = []
    for item in effects:
        decision = store.get_decision(item.decision_id)
        if decision is None:
            raise StoreIntegrityError(
                "build_run_report",
                f"Effect 缺少 Decision：{item.effect_id}",
            )
        basis = tuple(
            artifact
            for artifact_id in decision.decision_basis_artifact_ids
            if (artifact := store.get_artifact(artifact_id)) is not None
        )
        values.append(EffectAnalysisEvidence(item, decision, basis))
    return tuple(values)


def load_run_revocations(
    store: EventStore,
    scenario: Scenario,
    run_id: str,
) -> tuple[RunRevocationEvidence, ...]:
    """恢复 Skill 撤销事件及其 Scenario Session 索引。"""
    session_indexes = {session.id: index for index, session in enumerate(scenario.sessions)}
    values: list[RunRevocationEvidence] = []
    for revocation in store.iter_run_revocations(run_id):
        if revocation.target_kind is not RevocationTargetKind.PRINCIPAL:
            continue
        event = store.get_event(revocation.event_id)
        if event is None or event.session_id not in session_indexes:
            raise StoreIntegrityError(
                "build_run_report",
                f"撤销 Event 缺失或 Session 未声明：{revocation.event_id}",
            )
        values.append(
            RunRevocationEvidence(
                skill_id=revocation.target_id,
                revoke_event_id=revocation.event_id,
                session_index=session_indexes[event.session_id],
                revoked_at=revocation.timestamp,
            )
        )
    return tuple(values)
