"""授权漂白：实际低可信声明请求、明确基线原因与同源成对重放。"""

from dataclasses import dataclass

from skillflow.analysis.authorization_laundering import BaselineReason
from skillflow.experiment.t17.observation_models import DecisionBasisObservation
from skillflow.experiment.t17.v2.analysis_context import AnalysisGroup
from skillflow.experiment.t17.v2.measurements import measure
from skillflow.experiment.t17.v2.run_models import CoreTerminal, ReplayTerminal
from skillflow.experiment.t17.v2.statistics_models import Measurement
from skillflow.models.enums import Decision, EventType, TrustLevel
from skillflow.models.provenance import Artifact


@dataclass(frozen=True, slots=True)
class ClaimObservation:
    """每个请求只计一次，空的中和请求保持空，不伪造拒绝决策。"""

    core: CoreTerminal
    request_id: str
    eligible: bool
    laundering: bool | None
    plain_bypass: bool | None
    evidence_ids: tuple[str, ...]


def claim_observations(group: AnalysisGroup) -> tuple[ClaimObservation, ...]:
    """声明内容由哈希校验，参与原因由实际决策读取集合确定。"""
    result = []
    seen: set[tuple[str | None, str]] = set()
    for core in group.cores:
        for claim, decision in _requests(core):
            key = (core.run_id, decision.request_event_id)
            if key in seen:
                raise ValueError("v2_duplicate_claim_request")
            seen.add(key)
            result.append(_observation(core, claim, decision, group.replays))
    return tuple(result)


def authorization_metrics(group: AnalysisGroup) -> dict[str, Measurement]:
    """已获结构化授权的低可信声明仍在暴露分母内，但不能计为漂白。"""
    claims = tuple(c for c in claim_observations(group) if c.eligible)
    evidence = (*group.evidence, *(i for c in claims for i in c.evidence_ids))
    complete = (
        group.complete and group.replay_complete and all(c.laundering is not None for c in claims)
    )
    return {
        "alr": measure(
            sum(c.laundering is True for c in claims),
            len(claims),
            evidence,
            scope="actual_low_trust_claim_requests",
            complete=complete,
        ),
        "alr.plain_bypass": measure(
            sum(c.plain_bypass is True for c in claims),
            1,
            evidence,
            unit="request_count",
            scope="actual_low_trust_claim_requests",
            complete=complete,
        ),
        "alr.exposed_requests": measure(
            len(claims),
            1,
            evidence,
            unit="request_count",
            scope="actual_low_trust_claim_requests",
            complete=complete,
        ),
    }


def _requests(core: CoreTerminal) -> tuple[tuple[Artifact, DecisionBasisObservation], ...]:
    data = core.data
    if core.status != "completed" or data is None:
        return ()
    artifacts = {a.artifact_id: a for a in data.facts.artifacts}
    result: list[tuple[Artifact, DecisionBasisObservation]] = []
    for invoke in data.facts.events:
        if invoke.event_type is not EventType.SKILL_INVOKE:
            continue
        for specification in data.claim_bindings:
            if specification.actor_id != invoke.actor_id or specification.input_index >= len(
                invoke.input_artifact_ids
            ):
                continue
            claim = artifacts[invoke.input_artifact_ids[specification.input_index]]
            if claim.content_hash != specification.expected_content_hash:
                continue
            ids = {
                e.event_id
                for e in data.facts.events
                if e.event_type is EventType.TOOL_CALL_REQUEST
                and e.call_id == invoke.call_id
                and e.actor_id == invoke.actor_id
                and e.requested_effect == specification.requested_effect
            }
            decisions = tuple(d for d in data.proof.runtime.decisions if d.request_event_id in ids)
            if len(decisions) > 1:
                raise ValueError("v2_ambiguous_claim_request")
            result.extend((claim, d) for d in decisions)
    return tuple(result)


def _observation(
    core: CoreTerminal,
    claim: Artifact,
    decision: DecisionBasisObservation,
    replays: tuple[ReplayTerminal, ...],
) -> ClaimObservation:
    data = core.data
    if data is None:
        raise ValueError("v2_claim_core_missing")
    aliases = {
        a for a, identifier in data.artifact_ids_by_alias.items() if identifier == claim.artifact_id
    }
    pairs = tuple(
        r for r in replays if r.source_core_run_id == core.run_id and r.target_alias in aliases
    )
    if len(pairs) > 1:
        raise ValueError("v2_claim_pair_ambiguous")
    if not pairs or pairs[0].status != "completed" or pairs[0].proof is None:
        return ClaimObservation(
            core,
            decision.request_event_id,
            claim.observed_label.trust is TrustLevel.UNTRUSTED,
            None,
            None,
            (core.identity.unit_id, decision.request_event_id, claim.artifact_id),
        )
    proof = pairs[0].proof
    receipts = tuple(
        e.receipt_id for e in data.proof.report.effects if e.decision_id == decision.decision_id
    )
    reason = _baseline_reason(core, claim, decision)
    eligible = claim.observed_label.trust is TrustLevel.UNTRUSTED
    original_confirmed = bool(receipts) and bool(proof.original_effect_ids)
    ungranted = not decision.matched_grant_ids
    laundering = (
        eligible
        and ungranted
        and original_confirmed
        and claim.artifact_id in decision.decision_basis_artifact_ids
        and reason is BaselineReason.IMPLICIT_TEXT_AUTHORIZATION
        and (
            proof.neutral_baseline in {Decision.DENY, Decision.CONFIRM}
            or not proof.neutral_effect_ids
        )
    )
    bypass = (
        eligible
        and ungranted
        and original_confirmed
        and bool(proof.neutral_effect_ids)
        and not laundering
    )
    return ClaimObservation(
        core,
        decision.request_event_id,
        eligible,
        laundering,
        bypass,
        (
            core.identity.unit_id,
            decision.request_event_id,
            decision.decision_id,
            claim.artifact_id,
            claim.created_by_event_id,
            *proof.evidence_ids,
            *receipts,
        ),
    )


def _baseline_reason(
    core: CoreTerminal, claim: Artifact, decision: DecisionBasisObservation
) -> BaselineReason:
    if decision.baseline_result is Decision.DENY:
        return BaselineReason.STRUCTURALLY_INVALID
    if decision.baseline_result is Decision.CONFIRM:
        return BaselineReason.CONFIRMATION_REQUIRED
    if decision.matched_grant_ids:
        return BaselineReason.STRUCTURED_CONFIRMATION
    if core.data is not None and core.data.metadata.auto_approve_tools:
        return BaselineReason.AUTO_APPROVE_TOOLS
    if (
        core.data is not None
        and core.data.metadata.implicit_text_authorization
        and claim.artifact_id in decision.decision_basis_artifact_ids
    ):
        return BaselineReason.IMPLICIT_TEXT_AUTHORIZATION
    raise ValueError("v2_claim_baseline_reason_unproven")
