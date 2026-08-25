"""Manifest、Grant 与 Observed 来源的纯 PolicyEngine。"""

from skillflow.models.enums import Decision, TrustLevel
from skillflow.policy.matchers import match_grants, match_manifest
from skillflow.policy.models import PolicyEvaluation, PolicyRequest, ProvenanceEvidence
from skillflow.policy.reasons import PolicyReasonCode


class PolicyEngine:
    """在不读取 Oracle 的前提下计算结构化策略结果。"""

    def evaluate(self, request: PolicyRequest) -> PolicyEvaluation:
        """同时保留授权真值、策略建议、证据和失败原因。"""
        manifest = match_manifest(request.manifest, request.grant_request.effect)
        grants = match_grants(request.grants, request.grant_request)
        authorized = manifest.matched and bool(grants.matched_grant_ids)
        provenance_reasons = _provenance_reasons(request.provenance)
        reason_codes = (*manifest.reason_codes, *grants.reason_codes, *provenance_reasons)
        can_confirm = (
            manifest.matched
            and grants.reason_codes == (PolicyReasonCode.USER_GRANT_MISSING,)
            and not provenance_reasons
            and request.confirmation_allowed
        )
        if authorized and not provenance_reasons:
            policy_result = Decision.ALLOW
        else:
            policy_result = Decision.CONFIRM if can_confirm else Decision.DENY
        return PolicyEvaluation(
            policy_result=policy_result,
            authorized=authorized,
            manifest_id=manifest.manifest_id,
            manifest_matched=manifest.matched,
            valid_grant_matched=bool(grants.matched_grant_ids),
            matched_grant_ids=grants.matched_grant_ids,
            decision_basis_artifact_ids=request.provenance.artifact_ids,
            reason_codes=reason_codes,
        )


def _provenance_reasons(evidence: ProvenanceEvidence) -> tuple[PolicyReasonCode, ...]:
    reasons: list[PolicyReasonCode] = []
    if evidence.revoked_origins:
        reasons.append(PolicyReasonCode.ORIGIN_REVOKED)
    if evidence.trust_levels & {TrustLevel.UNTRUSTED, TrustLevel.UNKNOWN}:
        reasons.append(PolicyReasonCode.UNTRUSTED_ORIGIN)
    if not evidence.complete:
        reasons.append(PolicyReasonCode.PROVENANCE_INCOMPLETE)
    return tuple(reasons)
