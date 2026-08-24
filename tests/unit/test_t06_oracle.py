from datetime import UTC, datetime, timedelta

import pytest

from skillflow.models.authorization import AuthorizationGrant
from skillflow.models.effects import CapabilityEffect
from skillflow.models.enums import CapabilityAction, Decision, EnforcementMode, Lifetime
from skillflow.models.events import DecisionRecord
from skillflow.models.resources import ResourceRef
from skillflow.oracle.grants import OracleAuthorizationRequest, OracleGrantResolver

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def make_effect() -> CapabilityEffect:
    return CapabilityEffect(
        source=ResourceRef("workspace:/documents/report.txt"),
        action=CapabilityAction.FILE_READ,
        sink=ResourceRef("context:/task"),
        scope="exact-file",
        lifetime=Lifetime.CALL,
        sensitivity=1,
    )


def make_grant() -> AuthorizationGrant:
    return AuthorizationGrant(
        grant_id="grant-read-report",
        issuer_id="user-1",
        issuer_type="user",
        grantee_id="benign_reader",
        action=CapabilityAction.FILE_READ,
        source_pattern=ResourceRef("workspace:/documents/report.txt"),
        sink_pattern=ResourceRef("context:/task"),
        scope="exact-file",
        lifetime=Lifetime.TASK,
        task_id="task_t06",
        valid_from=NOW,
        expires_at=NOW + timedelta(hours=1),
    )


def make_request(
    *,
    permissions: tuple[CapabilityEffect, ...] | None = None,
    task_id: str = "task_t06",
    session_id: str = "session_1",
    call_id: str = "call-1",
    effect_time: datetime = NOW,
) -> OracleAuthorizationRequest:
    effect = make_effect()
    return OracleAuthorizationRequest(
        actor_id="benign_reader",
        effect=effect,
        manifest_permissions=(effect,) if permissions is None else permissions,
        task_id=task_id,
        session_id=session_id,
        call_id=call_id,
        effect_time=effect_time,
    )


def test_oracle_authorization_is_independent_from_policy_result() -> None:
    # Given: 同一真实 Grant/Manifest/Effect，以及两种相反的 PolicyEngine 结果
    resolver = OracleGrantResolver((make_grant(),))
    policy_decisions = (
        DecisionRecord(
            decision_id="decision-allow",
            request_event_id="request-1",
            enforcement_mode=EnforcementMode.MONITOR,
            baseline_result=Decision.ALLOW,
            policy_result=Decision.ALLOW,
            authorized=False,
            executed=True,
        ),
        DecisionRecord(
            decision_id="decision-deny",
            request_event_id="request-1",
            enforcement_mode=EnforcementMode.MONITOR,
            baseline_result=Decision.ALLOW,
            policy_result=Decision.DENY,
            authorized=False,
            executed=True,
        ),
    )

    # When: 改变 PolicyEngine 结果后，仍只把独立请求交给 Oracle
    resolutions = tuple(resolver.resolve(make_request()) for _ in policy_decisions)

    # Then: GT_auth 不读取 PolicyEngine，且真实双钥匙授权成立
    assert {decision.policy_result for decision in policy_decisions} == {
        Decision.ALLOW,
        Decision.DENY,
    }
    assert resolutions[0] == resolutions[1]
    assert resolutions[0].gt_auth is True
    assert resolutions[0].manifest_declared is True
    assert resolutions[0].matched_grant_ids == ("grant-read-report",)


def test_oracle_requires_manifest_and_grant_as_independent_keys() -> None:
    # Given: Grant 完全匹配，但 Manifest 没有声明该能力
    resolver = OracleGrantResolver((make_grant(),))

    # When: 解析 Oracle 授权
    result = resolver.resolve(make_request(permissions=()))

    # Then: Grant 仍可被识别，但 GT_auth 必须为 false
    assert result.manifest_declared is False
    assert result.matched_grant_ids == ("grant-read-report",)
    assert result.gt_auth is False


def test_oracle_enforces_task_lifetime_without_reading_observed_labels() -> None:
    # Given: task lifetime Grant 与当前 Task 不同
    resolver = OracleGrantResolver((make_grant(),))

    # When: 请求来自另一个 Task
    result = resolver.resolve(make_request(task_id="task_other"))

    # Then: 边界不匹配，Oracle 独立判定为未授权
    assert result.gt_auth is False
    assert result.matched_grant_ids == ()


@pytest.mark.parametrize(
    ("lifetime", "session_id", "call_id", "auth_request", "expected"),
    [
        (Lifetime.CALL, None, "call-1", make_request(), True),
        (Lifetime.CALL, None, "call-other", make_request(), False),
        (Lifetime.TASK, None, None, make_request(), True),
        (
            Lifetime.TASK,
            None,
            None,
            make_request(task_id="task-other"),
            False,
        ),
        (Lifetime.SESSION, "session_1", None, make_request(), True),
        (
            Lifetime.SESSION,
            "session_1",
            None,
            make_request(session_id="session-other"),
            False,
        ),
        (
            Lifetime.PERSISTENT,
            None,
            None,
            make_request(task_id="task-other", session_id="session-other"),
            True,
        ),
    ],
)
def test_oracle_honors_all_four_lifetime_boundaries(
    lifetime: Lifetime,
    session_id: str | None,
    call_id: str | None,
    auth_request: OracleAuthorizationRequest,
    expected: bool,
) -> None:
    # Given: 四值菱形 lifetime 中的一个 Grant
    payload = make_grant().model_dump(mode="json")
    payload.update({"lifetime": lifetime.value, "session_id": session_id, "call_id": call_id})
    grant = AuthorizationGrant.model_validate(payload)

    # When: Oracle 按该 lifetime 唯一对应的边界解析
    result = OracleGrantResolver((grant,)).resolve(auth_request)

    # Then: task/session 互不替代，persistent 不叠加旧 ID 边界
    assert result.gt_auth is expected


def test_oracle_rejects_expired_and_revoked_grants() -> None:
    # Given: 一个在 Effect 时点已过期的 Grant 和一个已撤销 Grant
    grant = make_grant()
    expired = OracleGrantResolver((grant,)).resolve(
        make_request(effect_time=grant.expires_at or NOW)
    )
    revoked = OracleGrantResolver((grant,), revoked_grant_ids=frozenset({grant.grant_id})).resolve(
        make_request()
    )

    # Then: 二者都不能成为 GT_auth
    assert expired.gt_auth is False
    assert revoked.gt_auth is False
