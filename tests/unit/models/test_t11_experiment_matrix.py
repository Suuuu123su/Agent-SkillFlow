import pytest
from pydantic import ValidationError

from skillflow.models.enums import EnforcementMode, ProvenanceMode
from skillflow.models.matrix import (
    ExperimentMatrix,
    HarnessFeature,
    HiaaCell,
    HiaaDesign,
    NeutralSkillPair,
    SkillControlProfile,
    SkillLengthInterval,
    build_hiaa_matrix,
)


def _profile(
    skill_id: str,
    *,
    dangerous_semantics_present: bool,
    content_length: int,
) -> SkillControlProfile:
    return SkillControlProfile(
        skill_id=skill_id,
        manifest_sha256="manifest-same",
        schema_sha256="schema-same",
        tool_registrations=("http_send",),
        content_length=content_length,
        dangerous_semantics_present=dangerous_semantics_present,
    )


def _pair(neutral: SkillControlProfile) -> NeutralSkillPair:
    return NeutralSkillPair(
        target=_profile(
            "target-skill",
            dangerous_semantics_present=True,
            content_length=1_000,
        ),
        neutral=neutral,
        length_interval=SkillLengthInterval(minimum=900, maximum=1_100),
    )


def _design(feature: HarnessFeature = HarnessFeature.SHARED_CONTEXT) -> HiaaDesign:
    return HiaaDesign(
        schema_version="0.1",
        id="shared-context-effect",
        target_scenario="scenarios/target.yaml",
        neutral_scenario="scenarios/neutral.yaml",
        seed=17,
        feature=feature,
        skill_pair=_pair(
            _profile(
                "neutral-skill",
                dangerous_semantics_present=False,
                content_length=980,
            )
        ),
        shared_context=True,
        persistent_memory=True,
        auto_approve_tools=False,
        enforcement_mode=EnforcementMode.MONITOR,
        provenance_mode=ProvenanceMode.PRESERVE,
        implicit_text_authorization=False,
    )


def test_hiaa_design_generates_the_complete_four_cell_matrix() -> None:
    # Given: 一个能力匹配的目标/中性 Skill 对和唯一待测 Harness 特性
    design = _design()

    # When: 自动构造四格矩阵
    matrix = build_hiaa_matrix(design)

    # Then: p00/p01/p10/p11 完整且只改变 Skill 语义与目标 Harness 特性
    assert tuple(variant.hiaa_cell for variant in matrix.variants) == tuple(HiaaCell)
    assert tuple(variant.target_skill_present for variant in matrix.variants) == (
        False,
        False,
        True,
        True,
    )
    assert tuple(variant.shared_context for variant in matrix.variants) == (
        False,
        True,
        False,
        True,
    )
    assert tuple(variant.scenario.root for variant in matrix.variants) == (
        "scenarios/neutral.yaml",
        "scenarios/neutral.yaml",
        "scenarios/target.yaml",
        "scenarios/target.yaml",
    )
    assert {variant.seed for variant in matrix.variants} == {17}
    assert {variant.persistent_memory for variant in matrix.variants} == {True}


@pytest.mark.parametrize(
    ("feature", "field"),
    [
        (HarnessFeature.SHARED_CONTEXT, "shared_context"),
        (HarnessFeature.PERSISTENT_MEMORY, "persistent_memory"),
        (HarnessFeature.AUTO_APPROVE_TOOLS, "auto_approve_tools"),
        (HarnessFeature.IMPLICIT_TEXT_AUTHORIZATION, "implicit_text_authorization"),
    ],
)
def test_each_supported_harness_feature_changes_only_its_four_cell_axis(
    feature: HarnessFeature,
    field: str,
) -> None:
    design = _design(feature)
    matrix = build_hiaa_matrix(design)
    controlled_fields = (
        "shared_context",
        "persistent_memory",
        "auto_approve_tools",
        "implicit_text_authorization",
    )

    assert tuple(getattr(variant, field) for variant in matrix.variants) == (
        False,
        True,
        False,
        True,
    )
    for unchanged_field in controlled_fields:
        if unchanged_field != field:
            expected = getattr(design, unchanged_field)
            assert {getattr(variant, unchanged_field) for variant in matrix.variants} == {expected}


def test_hiaa_matrix_rejects_a_hand_tampered_cell() -> None:
    payload = build_hiaa_matrix(_design()).model_dump(mode="python")
    variants = payload["variants"]
    assert isinstance(variants, tuple)
    variants[0]["seed"] = 18

    with pytest.raises(ValidationError, match="机械生成"):
        ExperimentMatrix.model_validate(payload)


@pytest.mark.parametrize(
    ("neutral", "message"),
    [
        (
            SkillControlProfile(
                skill_id="neutral-skill",
                manifest_sha256="manifest-different",
                schema_sha256="schema-same",
                tool_registrations=("http_send",),
                content_length=980,
                dangerous_semantics_present=False,
            ),
            "Manifest",
        ),
        (
            SkillControlProfile(
                skill_id="neutral-skill",
                manifest_sha256="manifest-same",
                schema_sha256="schema-different",
                tool_registrations=("http_send",),
                content_length=980,
                dangerous_semantics_present=False,
            ),
            "Schema",
        ),
        (
            SkillControlProfile(
                skill_id="neutral-skill",
                manifest_sha256="manifest-same",
                schema_sha256="schema-same",
                tool_registrations=("shell_exec",),
                content_length=980,
                dangerous_semantics_present=False,
            ),
            "工具注册",
        ),
        (
            _profile(
                "neutral-skill",
                dangerous_semantics_present=False,
                content_length=1_101,
            ),
            "长度区间",
        ),
    ],
)
def test_neutral_skill_rejects_non_matching_controls(
    neutral: SkillControlProfile,
    message: str,
) -> None:
    # Given/When/Then: 中性 Skill 不能借结构、能力或长度变化制造虚假对照
    with pytest.raises(ValidationError, match=message):
        _pair(neutral)


def test_neutral_skill_must_remove_only_the_dangerous_semantics() -> None:
    # Given/When/Then: 目标必须含危险语义，而中性版本必须明确移除它
    with pytest.raises(ValidationError, match="危险语义"):
        _pair(
            _profile(
                "neutral-skill",
                dangerous_semantics_present=True,
                content_length=980,
            )
        )
