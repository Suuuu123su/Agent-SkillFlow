from datetime import UTC, datetime, timedelta

import pytest

from skillflow.models.authorization import AuthorizationGrant
from skillflow.models.effects import CapabilityEffect
from skillflow.models.enums import CapabilityAction, Decision, Lifetime, Scope, TrustLevel
from skillflow.models.manifest import SkillManifest
from skillflow.models.resources import ResourceRef
from skillflow.policy import (
    AuthorizationBoundary,
    BaselineFacts,
    DecisionInputs,
    GrantMatchRequest,
    PolicyEngine,
    PolicyReasonCode,
    PolicyRequest,
    ProvenanceEvidence,
    combine_decisions,
    evaluate_baseline,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def capability() -> CapabilityEffect:
    return CapabilityEffect(
        source=ResourceRef("workspace:/report.txt"),
        action=CapabilityAction.FILE_READ,
        sink=ResourceRef("context:/task"),
        scope=Scope.EXACT_FILE,
        lifetime=Lifetime.CALL,
        sensitivity=1,
    )


def manifest(*, declared: bool = True) -> SkillManifest:
    return SkillManifest(
        schema_version="0.1",
        id="skill-a",
        requested_permissions=(capability(),) if declared else (),
    )


def grant(
    *,
    valid_from: datetime = NOW,
    expires_at: datetime | None = None,
) -> AuthorizationGrant:
    return AuthorizationGrant(
        grant_id="grant-1",
        issuer_id="user-1",
        issuer_type="user",
        grantee_id="skill-a",
        action=CapabilityAction.FILE_READ,
        source_pattern=ResourceRef("workspace:/report.txt"),
        sink_pattern=ResourceRef("context:/task"),
        scope=Scope.EXACT_FILE,
        lifetime=Lifetime.TASK,
        task_id="task-1",
        valid_from=valid_from,
        expires_at=expires_at,
    )


def policy_request(
    *,
    declared: bool = True,
    grants: tuple[AuthorizationGrant, ...] = (),
    confirmation_allowed: bool = True,
    provenance: ProvenanceEvidence | None = None,
) -> PolicyRequest:
    return PolicyRequest(
        manifest=manifest(declared=declared),
        grants=grants,
        grant_request=GrantMatchRequest(
            actor_id="skill-a",
            effect=capability(),
            boundary=AuthorizationBoundary(
                task_id="task-1",
                session_id="session-1",
                call_id="call-1",
                effect_time=NOW,
            ),
        ),
        provenance=ProvenanceEvidence() if provenance is None else provenance,
        confirmation_allowed=confirmation_allowed,
    )


@pytest.mark.parametrize(
    ("policy_input", "decision", "authorized", "reason"),
    [
        (policy_request(grants=(grant(),)), Decision.ALLOW, True, None),
        (
            policy_request(),
            Decision.CONFIRM,
            False,
            PolicyReasonCode.USER_GRANT_MISSING,
        ),
        (
            policy_request(confirmation_allowed=False),
            Decision.DENY,
            False,
            PolicyReasonCode.USER_GRANT_MISSING,
        ),
        (
            policy_request(declared=False, grants=(grant(),)),
            Decision.DENY,
            False,
            PolicyReasonCode.MANIFEST_PERMISSION_MISSING,
        ),
        (
            policy_request(
                grants=(
                    grant(
                        valid_from=NOW - timedelta(hours=2),
                        expires_at=NOW - timedelta(seconds=1),
                    ),
                )
            ),
            Decision.DENY,
            False,
            PolicyReasonCode.GRANT_EXPIRED,
        ),
    ],
)
def test_policy_engine_implements_the_double_key_truth_table(
    policy_input: PolicyRequest,
    decision: Decision,
    authorized: bool,
    reason: PolicyReasonCode | None,
) -> None:
    # Given: Manifest、Grant 与确认策略的一格真值表输入
    # When: 独立 PolicyEngine 评估
    result = PolicyEngine().evaluate(policy_input)

    # Then: policy_result 与 authorized 不互相覆盖
    assert result.policy_result is decision
    assert result.authorized is authorized
    assert reason is None or reason in result.reason_codes


@pytest.mark.parametrize(
    ("evidence", "reason"),
    [
        (
            ProvenanceEvidence(
                artifact_ids=("artifact-1",),
                origins=frozenset({"skill-old"}),
                trust_levels=frozenset({TrustLevel.USER}),
                revoked_origins=frozenset({"skill-old"}),
            ),
            PolicyReasonCode.ORIGIN_REVOKED,
        ),
        (
            ProvenanceEvidence(
                artifact_ids=("artifact-1",),
                origins=frozenset({"skill-a"}),
                trust_levels=frozenset({TrustLevel.UNTRUSTED}),
            ),
            PolicyReasonCode.UNTRUSTED_ORIGIN,
        ),
        (
            ProvenanceEvidence(
                artifact_ids=("artifact-1",),
                origins=frozenset(),
                trust_levels=frozenset({TrustLevel.USER}),
                complete=False,
            ),
            PolicyReasonCode.PROVENANCE_INCOMPLETE,
        ),
    ],
)
def test_policy_denies_bad_provenance_without_rewriting_authorization(
    evidence: ProvenanceEvidence,
    reason: PolicyReasonCode,
) -> None:
    # Given: Manifest 与 Grant 有效，但来源证据不满足策略
    result = PolicyEngine().evaluate(policy_request(grants=(grant(),), provenance=evidence))

    # When/Then: authorized 保持真实，policy 单独拒绝并指出来源原因
    assert result.authorized
    assert result.policy_result is Decision.DENY
    assert reason in result.reason_codes
    assert result.decision_basis_artifact_ids == ("artifact-1",)


@pytest.mark.parametrize(
    ("facts", "expected"),
    [
        (
            BaselineFacts(
                structurally_valid=False,
                structured_confirmation=True,
                auto_approve_tools=True,
                implicit_text_authorization=True,
                text_claim_artifact_ids=("claim-1",),
            ),
            Decision.DENY,
        ),
        (BaselineFacts(structured_confirmation=True), Decision.ALLOW),
        (BaselineFacts(auto_approve_tools=True), Decision.ALLOW),
        (
            BaselineFacts(
                implicit_text_authorization=True,
                text_claim_artifact_ids=("claim-1",),
            ),
            Decision.ALLOW,
        ),
        (BaselineFacts(implicit_text_authorization=True), Decision.CONFIRM),
        (BaselineFacts(), Decision.CONFIRM),
    ],
)
def test_baseline_priority_is_fixed(facts: BaselineFacts, expected: Decision) -> None:
    # Given/When: 一组基线事实按固定优先级求值
    result = evaluate_baseline(facts)

    # Then: 文本开关本身不会在没有相关 Artifact 时自动批准
    assert result.result is expected


@pytest.mark.parametrize(
    ("mode", "baseline", "policy", "executed"),
    [
        ("monitor", Decision.ALLOW, Decision.DENY, True),
        ("monitor", Decision.CONFIRM, Decision.ALLOW, False),
        ("enforce", Decision.ALLOW, Decision.ALLOW, True),
        ("enforce", Decision.ALLOW, Decision.CONFIRM, False),
        ("enforce", Decision.DENY, Decision.ALLOW, False),
    ],
)
def test_monitor_and_enforce_change_execution_not_policy_truth(
    mode: str,
    baseline: Decision,
    policy: Decision,
    executed: bool,
) -> None:
    # Given: 相同 baseline/policy 真值与不同执行模式
    inputs = DecisionInputs.model_validate(
        {
            "enforcement_mode": mode,
            "baseline_result": baseline,
            "policy_result": policy,
            "authorized": False,
            "manifest_id": "skill-a",
            "decision_basis_artifact_ids": ["argument-1"],
            "matched_grant_ids": [],
            "reason_codes": [PolicyReasonCode.USER_GRANT_MISSING],
        }
    )

    # When: 组合最终 Tool 决策
    result = combine_decisions(inputs)

    # Then: monitor 不洗白授权，enforce 仅双 ALLOW 执行
    assert result.executed is executed
    assert not result.authorized
    assert result.policy_result is policy
