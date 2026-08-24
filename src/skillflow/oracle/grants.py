"""不读取 PolicyEngine 或 Observed 标签的 Oracle Grant 解析器。"""

from dataclasses import dataclass
from datetime import datetime
from typing import assert_never

from skillflow.models.authorization import AuthorizationGrant
from skillflow.models.effects import CapabilityEffect
from skillflow.models.enums import Lifetime, lifetime_covers
from skillflow.models.resources import ResourceRef


@dataclass(frozen=True, slots=True)
class OracleAuthorizationRequest:
    """独立 GT_auth 计算所需的真实边界。"""

    actor_id: str
    effect: CapabilityEffect
    manifest_permissions: tuple[CapabilityEffect, ...]
    task_id: str
    session_id: str
    call_id: str
    effect_time: datetime


@dataclass(frozen=True, slots=True)
class OracleAuthorizationResult:
    """Manifest 与 Grant 两把钥匙的机械结果。"""

    gt_auth: bool
    manifest_declared: bool
    matched_grant_ids: tuple[str, ...]


class OracleGrantResolver:
    """只从预注册 Grant、Manifest 和当前 Effect 计算真值。"""

    def __init__(
        self,
        grants: tuple[AuthorizationGrant, ...],
        revoked_grant_ids: frozenset[str] = frozenset(),
    ) -> None:
        """复制不可变 Grant 集合及事件时点前已撤销 ID。"""
        self._grants = tuple(grants)
        self._revoked_grant_ids = frozenset(revoked_grant_ids)

    def resolve(self, request: OracleAuthorizationRequest) -> OracleAuthorizationResult:
        """完全不接收 baseline、policy 或 observed authorization。"""
        manifest_declared = any(
            _capability_covers(permission, request.effect)
            for permission in request.manifest_permissions
        )
        matches = tuple(
            grant.grant_id for grant in self._grants if self._grant_matches(grant, request)
        )
        return OracleAuthorizationResult(
            gt_auth=manifest_declared and bool(matches),
            manifest_declared=manifest_declared,
            matched_grant_ids=matches,
        )

    def _grant_matches(
        self,
        grant: AuthorizationGrant,
        request: OracleAuthorizationRequest,
    ) -> bool:
        effect = request.effect
        return (
            grant.grant_id not in self._revoked_grant_ids
            and grant.grantee_id == request.actor_id
            and grant.action is effect.action
            and _resource_covers(grant.source_pattern, effect.source)
            and grant.sink_pattern.matches_exact(effect.sink)
            and grant.scope == effect.scope
            and lifetime_covers(grant.lifetime, effect.lifetime)
            and _boundary_matches(grant, request)
            and grant.valid_from <= request.effect_time
            and (grant.expires_at is None or request.effect_time < grant.expires_at)
        )


def _capability_covers(declared: CapabilityEffect, requested: CapabilityEffect) -> bool:
    return (
        declared.action is requested.action
        and _resource_covers(declared.source, requested.source)
        and declared.sink.matches_exact(requested.sink)
        and declared.scope == requested.scope
        and lifetime_covers(declared.lifetime, requested.lifetime)
        and declared.sensitivity >= requested.sensitivity
    )


def _resource_covers(pattern: ResourceRef | None, requested: ResourceRef | None) -> bool:
    if pattern is None or requested is None:
        return pattern is None and requested is None
    return pattern.matches_exact(requested)


def _boundary_matches(
    grant: AuthorizationGrant,
    request: OracleAuthorizationRequest,
) -> bool:
    match grant.lifetime:
        case Lifetime.CALL:
            return grant.call_id == request.call_id
        case Lifetime.TASK:
            return grant.task_id == request.task_id
        case Lifetime.SESSION:
            return grant.session_id == request.session_id
        case Lifetime.PERSISTENT:
            return True
        case _ as unreachable:
            assert_never(unreachable)
