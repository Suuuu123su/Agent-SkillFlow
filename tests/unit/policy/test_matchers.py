from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

import pytest

from skillflow.models.authorization import AuthorizationGrant
from skillflow.models.effects import CapabilityEffect
from skillflow.models.enums import CapabilityAction, Lifetime, Scope
from skillflow.models.resources import ResourceRef
from skillflow.policy import (
    AuthorizationBoundary,
    GrantMatchRequest,
    PolicyReasonCode,
    match_grants,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class GrantFixture:
    grantee_id: str = "skill-a"
    action: CapabilityAction = CapabilityAction.FILE_READ
    lifetime: Lifetime = Lifetime.TASK
    task_id: str = "task-1"
    session_id: str | None = "session-1"
    call_id: str | None = "call-1"
    source: str | None = "workspace:/reports/a.txt"
    sink: str = "context:/task"
    scope: Scope = Scope.EXACT_FILE
    valid_from: datetime = NOW
    expires_at: datetime | None = NOW + timedelta(hours=1)


DEFAULT_GRANT_FIXTURE: Final = GrantFixture()


def effect(
    *,
    source: str | None = "workspace:/reports/a.txt",
    sink: str = "context:/task",
    lifetime: Lifetime = Lifetime.CALL,
) -> CapabilityEffect:
    return CapabilityEffect(
        source=None if source is None else ResourceRef(source),
        action=CapabilityAction.FILE_READ,
        sink=ResourceRef(sink),
        scope=Scope.EXACT_FILE,
        lifetime=lifetime,
        sensitivity=2,
    )


def grant(fixture: GrantFixture = DEFAULT_GRANT_FIXTURE) -> AuthorizationGrant:
    return AuthorizationGrant(
        grant_id=f"grant-{fixture.lifetime.value}",
        issuer_id="user-1",
        issuer_type="user",
        grantee_id=fixture.grantee_id,
        action=fixture.action,
        source_pattern=None if fixture.source is None else ResourceRef(fixture.source),
        sink_pattern=ResourceRef(fixture.sink),
        scope=fixture.scope,
        lifetime=fixture.lifetime,
        task_id=fixture.task_id,
        session_id=fixture.session_id,
        call_id=fixture.call_id,
        valid_from=fixture.valid_from,
        expires_at=fixture.expires_at,
    )


def request(
    *,
    requested: CapabilityEffect | None = None,
    task_id: str = "task-1",
    session_id: str = "session-1",
    call_id: str = "call-1",
    revoked: frozenset[str] = frozenset(),
) -> GrantMatchRequest:
    return GrantMatchRequest(
        actor_id="skill-a",
        effect=effect() if requested is None else requested,
        boundary=AuthorizationBoundary(
            task_id=task_id,
            session_id=session_id,
            call_id=call_id,
            effect_time=NOW,
        ),
        revoked_grant_ids=revoked,
    )


@pytest.mark.parametrize(
    ("candidate", "task_id", "session_id", "call_id"),
    [
        (
            grant(GrantFixture(lifetime=Lifetime.CALL)),
            "different-task",
            "different-session",
            "call-1",
        ),
        (
            grant(GrantFixture(lifetime=Lifetime.TASK)),
            "task-1",
            "different-session",
            "different-call",
        ),
        (
            grant(GrantFixture(lifetime=Lifetime.SESSION)),
            "different-task",
            "session-1",
            "different-call",
        ),
        (
            grant(GrantFixture(lifetime=Lifetime.PERSISTENT)),
            "different-task",
            "different-session",
            "different-call",
        ),
    ],
)
def test_grant_lifetime_matches_only_its_own_boundary(
    candidate: AuthorizationGrant,
    task_id: str,
    session_id: str,
    call_id: str,
) -> None:
    # Given: 四种 lifetime 的 Grant 与无关边界 ID
    # When: 按该 lifetime 唯一相关的边界进行匹配
    result = match_grants(
        (candidate,),
        request(task_id=task_id, session_id=session_id, call_id=call_id),
    )

    # Then: call/task/session/persistent 均遵守各自边界合同
    assert result.matched_grant_ids == (candidate.grant_id,)
    assert result.reason_codes == ()


@pytest.mark.parametrize(
    ("candidate", "changes", "reason"),
    [
        (
            grant(GrantFixture(lifetime=Lifetime.CALL)),
            {"call_id": "call-2"},
            PolicyReasonCode.CROSS_CALL_USE,
        ),
        (
            grant(GrantFixture(lifetime=Lifetime.TASK)),
            {"task_id": "task-2"},
            PolicyReasonCode.CROSS_TASK_USE,
        ),
        (
            grant(GrantFixture(lifetime=Lifetime.SESSION)),
            {"session_id": "session-2"},
            PolicyReasonCode.CROSS_SESSION_USE,
        ),
    ],
)
def test_grant_reports_the_exact_cross_boundary_reason(
    candidate: AuthorizationGrant,
    changes: dict[str, str],
    reason: PolicyReasonCode,
) -> None:
    # Given: 一个边界受限 Grant
    # When: 只改变其 lifetime 对应的边界 ID
    result = match_grants((candidate,), request(**changes))

    # Then: 返回稳定且具体的跨界 reason code
    assert result.matched_grant_ids == ()
    assert result.reason_codes == (reason,)


def test_task_and_session_lifetimes_are_incomparable() -> None:
    # Given: task Grant 与 session Effect
    candidate = grant(GrantFixture(lifetime=Lifetime.TASK))

    # When: 即使 task_id 相同也尝试扩大为 session lifetime
    result = match_grants(
        (candidate,),
        request(requested=effect(lifetime=Lifetime.SESSION)),
    )

    # Then: 菱形偏序拒绝 task→session
    assert result.reason_codes == (PolicyReasonCode.CROSS_TASK_USE,)


@pytest.mark.parametrize(
    ("candidate", "revoked", "reason"),
    [
        (
            grant(
                GrantFixture(
                    valid_from=NOW - timedelta(hours=2),
                    expires_at=NOW - timedelta(seconds=1),
                )
            ),
            frozenset(),
            PolicyReasonCode.GRANT_EXPIRED,
        ),
        (
            grant(),
            frozenset({"grant-task"}),
            PolicyReasonCode.GRANT_REVOKED,
        ),
        (
            grant(GrantFixture(source="workspace:/reports/a.txt.bak")),
            frozenset(),
            PolicyReasonCode.RESOURCE_SCOPE_EXCEEDED,
        ),
        (
            grant(GrantFixture(sink="context:/other")),
            frozenset(),
            PolicyReasonCode.SINK_SCOPE_EXCEEDED,
        ),
        (
            grant(GrantFixture(scope=Scope.EXACT_KEY)),
            frozenset(),
            PolicyReasonCode.RESOURCE_SCOPE_EXCEEDED,
        ),
        (
            grant(
                GrantFixture(
                    valid_from=NOW + timedelta(seconds=1),
                    expires_at=NOW + timedelta(hours=1),
                )
            ),
            frozenset(),
            PolicyReasonCode.GRANT_NOT_YET_VALID,
        ),
    ],
)
def test_grant_matcher_reports_scope_time_and_revoke_failures(
    candidate: AuthorizationGrant,
    revoked: frozenset[str],
    reason: PolicyReasonCode,
) -> None:
    # Given: 一个在单一维度无效的相关 Grant
    # When: 执行完整 Grant 匹配
    result = match_grants((candidate,), request(revoked=revoked))

    # Then: 不回退成模糊的 USER_GRANT_MISSING
    assert result.matched_grant_ids == ()
    assert result.reason_codes == (reason,)


@pytest.mark.parametrize(
    "candidate",
    [
        grant(GrantFixture(grantee_id="skill-b")),
        grant(GrantFixture(action=CapabilityAction.FILE_WRITE)),
    ],
)
def test_grant_matcher_reports_missing_relevant_principal_or_action(
    candidate: AuthorizationGrant,
) -> None:
    # Given: 只有其他主体或其他 action 的 Grant

    # When: skill-a 请求能力
    result = match_grants((candidate,), request())

    # Then: 明确报告真实用户 Grant 缺失
    assert result.reason_codes == (PolicyReasonCode.USER_GRANT_MISSING,)
