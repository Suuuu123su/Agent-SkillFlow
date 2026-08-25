"""Manifest capability 与 AuthorizationGrant 的独立 matcher。"""

from collections.abc import Iterable
from typing import Final, assert_never

from skillflow.models.authorization import AuthorizationGrant
from skillflow.models.effects import CapabilityEffect
from skillflow.models.enums import Lifetime, lifetime_covers, scope_covers
from skillflow.models.manifest import SkillManifest
from skillflow.models.resources import ResourceRef
from skillflow.policy.models import GrantMatch, GrantMatchRequest, ManifestMatch
from skillflow.policy.reasons import PolicyReasonCode

REASON_ORDER: Final = {reason: index for index, reason in enumerate(PolicyReasonCode)}


def match_manifest(manifest: SkillManifest, effect: CapabilityEffect) -> ManifestMatch:
    """判断一个 Manifest 是否声明了请求 Effect。"""
    permissions = manifest.requested_permissions or manifest.declared_permissions
    matched = tuple(
        index
        for index, permission in enumerate(permissions)
        if _capability_covers(permission, effect)
    )
    reasons = () if matched else (PolicyReasonCode.MANIFEST_PERMISSION_MISSING,)
    return ManifestMatch(
        matched=bool(matched),
        manifest_id=manifest.id,
        permission_indexes=matched,
        reason_codes=reasons,
    )


def match_grants(
    grants: tuple[AuthorizationGrant, ...],
    request: GrantMatchRequest,
) -> GrantMatch:
    """聚合全部相关 Grant，任一完整匹配即视为真实授权。"""
    relevant = tuple(
        grant
        for grant in grants
        if grant.grantee_id == request.actor_id and grant.action is request.effect.action
    )
    if not relevant:
        return GrantMatch((), (PolicyReasonCode.USER_GRANT_MISSING,))

    evaluated = tuple((grant, _grant_reasons(grant, request)) for grant in relevant)
    matches = tuple(grant.grant_id for grant, reasons in evaluated if not reasons)
    if matches:
        return GrantMatch(matches, ())
    return GrantMatch((), _ordered_unique(reason for _, reasons in evaluated for reason in reasons))


def _capability_covers(granted: CapabilityEffect, requested: CapabilityEffect) -> bool:
    return (
        granted.action is requested.action
        and _resource_covers(granted.source, requested.source)
        and granted.sink.matches_exact(requested.sink)
        and scope_covers(granted.scope, requested.scope)
        and lifetime_covers(granted.lifetime, requested.lifetime)
        and granted.sensitivity >= requested.sensitivity
    )


def _grant_reasons(
    grant: AuthorizationGrant,
    request: GrantMatchRequest,
) -> tuple[PolicyReasonCode, ...]:
    effect = request.effect
    reasons: list[PolicyReasonCode] = []
    if not _resource_covers(grant.source_pattern, effect.source):
        reasons.append(PolicyReasonCode.RESOURCE_SCOPE_EXCEEDED)
    if not grant.sink_pattern.matches_exact(effect.sink):
        reasons.append(PolicyReasonCode.SINK_SCOPE_EXCEEDED)
    if not scope_covers(grant.scope, effect.scope):
        reasons.append(PolicyReasonCode.RESOURCE_SCOPE_EXCEEDED)
    lifetime_reason = _lifetime_reason(grant, request)
    if lifetime_reason is not None:
        reasons.append(lifetime_reason)
    boundary = request.boundary
    if boundary.effect_time < grant.valid_from:
        reasons.append(PolicyReasonCode.GRANT_NOT_YET_VALID)
    if grant.expires_at is not None and boundary.effect_time >= grant.expires_at:
        reasons.append(PolicyReasonCode.GRANT_EXPIRED)
    if grant.grant_id in request.revoked_grant_ids:
        reasons.append(PolicyReasonCode.GRANT_REVOKED)
    return _ordered_unique(reasons)


def _lifetime_reason(
    grant: AuthorizationGrant,
    request: GrantMatchRequest,
) -> PolicyReasonCode | None:
    if not lifetime_covers(grant.lifetime, request.effect.lifetime):
        return _cross_boundary_reason(grant.lifetime)
    boundary = request.boundary
    match grant.lifetime:
        case Lifetime.CALL:
            matches = grant.call_id == boundary.call_id
        case Lifetime.TASK:
            matches = grant.task_id == boundary.task_id
        case Lifetime.SESSION:
            matches = grant.session_id == boundary.session_id
        case Lifetime.PERSISTENT:
            matches = True
        case _ as unreachable:
            assert_never(unreachable)
    return None if matches else _cross_boundary_reason(grant.lifetime)


def _cross_boundary_reason(lifetime: Lifetime) -> PolicyReasonCode:
    match lifetime:
        case Lifetime.CALL:
            return PolicyReasonCode.CROSS_CALL_USE
        case Lifetime.TASK:
            return PolicyReasonCode.CROSS_TASK_USE
        case Lifetime.SESSION:
            return PolicyReasonCode.CROSS_SESSION_USE
        case Lifetime.PERSISTENT:
            raise AssertionError
        case _ as unreachable:
            assert_never(unreachable)


def _resource_covers(pattern: ResourceRef | None, requested: ResourceRef | None) -> bool:
    if pattern is None or requested is None:
        return pattern is None and requested is None
    return pattern.matches_exact(requested)


def _ordered_unique(reasons: Iterable[PolicyReasonCode]) -> tuple[PolicyReasonCode, ...]:
    return tuple(sorted(set(reasons), key=REASON_ORDER.__getitem__))
