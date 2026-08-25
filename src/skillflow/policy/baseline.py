"""第 5.6 节 baseline 与执行真值表。"""

from typing import assert_never

from skillflow.models.enums import Decision, EnforcementMode
from skillflow.policy.models import (
    BaselineEvaluation,
    BaselineFacts,
    DecisionInputs,
    DecisionPlan,
)


def evaluate_baseline(facts: BaselineFacts) -> BaselineEvaluation:
    """按固定优先级计算未加固 Harness 的原决定。"""
    if not facts.structurally_valid:
        return BaselineEvaluation(Decision.DENY)
    if facts.structured_confirmation or facts.auto_approve_tools:
        return BaselineEvaluation(Decision.ALLOW)
    text_allowed = facts.implicit_text_authorization and bool(facts.text_claim_artifact_ids)
    if text_allowed:
        return BaselineEvaluation(Decision.ALLOW, facts.text_claim_artifact_ids)
    return BaselineEvaluation(Decision.CONFIRM)


def combine_decisions(inputs: DecisionInputs) -> DecisionPlan:
    """组合 baseline/policy，但不让执行模式改写授权事实。"""
    match inputs.enforcement_mode:
        case EnforcementMode.MONITOR:
            executed = inputs.baseline_result is Decision.ALLOW
        case EnforcementMode.ENFORCE:
            executed = (
                inputs.baseline_result is Decision.ALLOW and inputs.policy_result is Decision.ALLOW
            )
        case _ as unreachable:
            assert_never(unreachable)
    return DecisionPlan(
        enforcement_mode=inputs.enforcement_mode,
        baseline_result=inputs.baseline_result,
        policy_result=inputs.policy_result,
        authorized=inputs.authorized,
        executed=executed,
        manifest_id=inputs.manifest_id,
        decision_basis_artifact_ids=inputs.decision_basis_artifact_ids,
        matched_grant_ids=inputs.matched_grant_ids,
        reason_codes=tuple(reason.value for reason in inputs.reason_codes),
    )
