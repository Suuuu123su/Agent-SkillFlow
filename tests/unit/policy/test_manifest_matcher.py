import pytest
from pydantic import ValidationError

from skillflow.models.effects import CapabilityEffect
from skillflow.models.enums import CapabilityAction, Lifetime, Scope, scope_covers
from skillflow.models.manifest import SkillManifest
from skillflow.models.resources import ResourceRef
from skillflow.policy import PolicyReasonCode, match_manifest


def effect(
    *,
    source: str | None = "workspace:/reports/a.txt",
    lifetime: Lifetime = Lifetime.CALL,
) -> CapabilityEffect:
    return CapabilityEffect(
        source=None if source is None else ResourceRef(source),
        action=CapabilityAction.FILE_READ,
        sink=ResourceRef("context:/task"),
        scope=Scope.EXACT_FILE,
        lifetime=lifetime,
        sensitivity=2,
    )


def test_scope_is_a_closed_discrete_partial_order() -> None:
    # Given: MVP 冻结的四种精确 Scope
    scopes = tuple(Scope)

    # When/Then: 每个 Scope 只覆盖自身，不能按字符串或枚举顺序放大
    assert {scope.value for scope in scopes} == {
        "exact-file",
        "exact-key",
        "exact-sink",
        "command",
    }
    assert all(
        scope_covers(granted, requested) is (granted is requested)
        for granted in scopes
        for requested in scopes
    )


def test_unknown_scope_is_rejected_at_the_model_boundary() -> None:
    # Given/When/Then: 未知 Scope 不进入 matcher
    with pytest.raises(ValidationError):
        CapabilityEffect.model_validate(
            {
                **effect().model_dump(mode="json"),
                "scope": "directory-by-prefix",
            }
        )


def test_manifest_matcher_applies_both_resource_and_lifetime_coverage() -> None:
    # Given: 声明 task lifetime 的精确单文件权限
    manifest = SkillManifest(
        schema_version="0.1",
        id="skill-a",
        requested_permissions=(effect(lifetime=Lifetime.TASK),),
    )

    # When: 请求同一文件的 call lifetime
    result = match_manifest(manifest, effect())

    # Then: task 覆盖 call，且返回稳定的 Manifest 追踪信息
    assert result.matched
    assert result.manifest_id == "skill-a"
    assert result.permission_indexes == (0,)
    assert result.reason_codes == ()


def test_manifest_exact_resource_does_not_cover_an_adjacent_prefix() -> None:
    # Given: Manifest 只声明 a.txt
    manifest = SkillManifest(
        schema_version="0.1",
        id="skill-a",
        requested_permissions=(effect(),),
    )

    # When: 请求 a.txt.bak
    result = match_manifest(manifest, effect(source="workspace:/reports/a.txt.bak"))

    # Then: 字符串前缀不能冒充路径覆盖
    assert not result.matched
    assert result.reason_codes == (PolicyReasonCode.MANIFEST_PERMISSION_MISSING,)


def test_manifest_scope_does_not_cross_the_discrete_antichain() -> None:
    # Given: Manifest 声明 exact-key，但 Effect 请求 exact-file
    declared = effect().model_copy(update={"scope": Scope.EXACT_KEY})
    manifest = SkillManifest(
        schema_version="0.1",
        id="skill-a",
        requested_permissions=(declared,),
    )

    # When/Then: Scope 不能靠枚举位置或字符串相似度放大
    result = match_manifest(manifest, effect())
    assert not result.matched
    assert result.reason_codes == (PolicyReasonCode.MANIFEST_PERMISSION_MISSING,)
