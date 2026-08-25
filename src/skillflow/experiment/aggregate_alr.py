"""从标准 RunResult/ReplayResult 构造收紧后的 ALR 暴露事实。"""

from skillflow.analysis.authorization_laundering import (
    AuthorizationAttemptFact,
    AuthorizationClaimNeutralization,
    BaselineReason,
)
from skillflow.models.matrix_axes import AuthorizationCondition
from skillflow.models.reports import ReplayRiskReport, RunRiskReport


def authorization_attempts(
    runs: tuple[RunRiskReport, ...],
    replays: tuple[ReplayRiskReport, ...],
) -> tuple[AuthorizationAttemptFact, ...]:
    """只保留具备声明、决策依据、Receipt 与同输入中和证据的授权尝试。"""
    indexed = {
        (replay.source_run_id, replay.target_alias): replay
        for replay in replays
        if replay.source_run_id is not None and replay.target_alias is not None
    }
    attempts: list[AuthorizationAttemptFact] = []
    for run in runs:
        reason = _baseline_reason(run.authorization_condition)
        if reason is None:
            continue
        for artifact in run.counterfactual_artifacts:
            replay = indexed.get((run.run_id, artifact.alias))
            if replay is None or replay.neutral_baseline_result is None:
                continue
            for effect in run.effects:
                basis_ids = tuple(item.artifact_id for item in effect.decision_basis_artifacts)
                if artifact.artifact_id not in basis_ids:
                    continue
                neutralization = None
                if replay.neutralization_preserves_other_inputs:
                    neutralization = AuthorizationClaimNeutralization(
                        replay_id=replay.replay_id,
                        neutralized_claim_artifact_id=artifact.artifact_id,
                        original_non_claim_inputs_hash=replay.replay_id,
                        neutral_non_claim_inputs_hash=replay.replay_id,
                    )
                attempts.append(
                    AuthorizationAttemptFact(
                        authorization_request_id=effect.request_event_id,
                        has_matching_grant=bool(effect.matched_grant_ids),
                        authorization_claim_artifact_id=artifact.artifact_id,
                        authorization_claim_trust=artifact.trust,
                        decision_basis_artifact_ids=basis_ids,
                        baseline_reason=reason,
                        original_receipt_ids=(effect.receipt_id,),
                        neutralization=neutralization,
                        neutral_baseline_result=replay.neutral_baseline_result,
                        neutral_receipt_ids=replay.neutral_receipt_ids,
                        evidence_ids=(effect.decision_id, replay.replay_id),
                    )
                )
    return tuple(attempts)


def _baseline_reason(condition: AuthorizationCondition) -> BaselineReason | None:
    if condition is AuthorizationCondition.IMPLICIT_TEXT:
        return BaselineReason.IMPLICIT_TEXT_AUTHORIZATION
    if condition is AuthorizationCondition.STRUCTURED_CONFIRMATION:
        return BaselineReason.STRUCTURED_CONFIRMATION
    return None
