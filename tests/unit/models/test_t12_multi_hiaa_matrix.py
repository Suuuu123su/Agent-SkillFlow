import pytest
from pydantic import ValidationError

from skillflow.models.enums import CapabilityAction, EnforcementMode, ProvenanceMode
from skillflow.models.matrix import (
    ExperimentMatrix,
    HarnessFeature,
    HiaaDesign,
    NeutralSkillPair,
    SkillControlProfile,
    SkillLengthInterval,
    build_hiaa_matrix,
)
from skillflow.models.resources import ResourceRef
from skillflow.models.scenario_parts import EffectSelector


def test_mvp_matrix_accepts_two_independent_hiaa_four_grids() -> None:
    context = _design("context-effect", 17)
    tool_return = _design("tool-return-effect", 23)
    variants = tuple(
        variant.model_copy(
            update={
                "variant": f"{design.id}-{variant.variant}",
                "hiaa_design_id": design.id,
            }
        )
        for design in (context, tool_return)
        for variant in build_hiaa_matrix(design).variants
    )

    matrix = ExperimentMatrix(
        schema_version="0.1",
        id="t12-two-four-grids",
        variants=variants,
        hiaa_designs=(context, tool_return),
        determinism_repeats=5,
    )

    assert len(matrix.variants) == 8
    assert {variant.hiaa_design_id for variant in matrix.variants} == {
        "context-effect",
        "tool-return-effect",
    }


def test_multi_hiaa_matrix_rejects_a_mismatched_selector() -> None:
    design = _design("context-effect", 17)
    variants = tuple(
        variant.model_copy(
            update={
                "variant": f"{design.id}-{variant.variant}",
                "hiaa_design_id": design.id,
            }
        )
        for variant in build_hiaa_matrix(design).variants
    )
    tampered = variants[0].model_copy(
        update={
            "harm_selector": EffectSelector(
                alias="other-harm",
                action=CapabilityAction.NETWORK_SEND,
                source_pattern=ResourceRef("context:/task"),
                sink_pattern=ResourceRef("mock://other"),
            )
        }
    )

    with pytest.raises(ValidationError, match="机械生成"):
        ExperimentMatrix(
            schema_version="0.1",
            id="t12-invalid-four-grid",
            variants=(tampered, *variants[1:]),
            hiaa_designs=(design,),
        )


def _design(identifier: str, seed: int) -> HiaaDesign:
    return HiaaDesign(
        schema_version="0.1",
        id=identifier,
        target_scenario="scenarios/target.yaml",
        neutral_scenario="scenarios/neutral.yaml",
        seed=seed,
        feature=HarnessFeature.SHARED_CONTEXT,
        harm_selector=EffectSelector(
            alias="harm",
            action=CapabilityAction.NETWORK_SEND,
            source_pattern=ResourceRef("context:/task"),
            sink_pattern=ResourceRef("mock://harm"),
        ),
        skill_pair=NeutralSkillPair(
            target=_profile("target", dangerous=True),
            neutral=_profile("neutral", dangerous=False),
            length_interval=SkillLengthInterval(minimum=900, maximum=1_100),
        ),
        shared_context=True,
        persistent_memory=True,
        auto_approve_tools=False,
        enforcement_mode=EnforcementMode.MONITOR,
        provenance_mode=ProvenanceMode.PRESERVE,
        implicit_text_authorization=False,
    )


def _profile(skill_id: str, *, dangerous: bool) -> SkillControlProfile:
    return SkillControlProfile(
        skill_id=skill_id,
        manifest_sha256="manifest-same",
        schema_sha256="schema-same",
        tool_registrations=("http_send",),
        content_length=1_000,
        dangerous_semantics_present=dangerous,
    )
