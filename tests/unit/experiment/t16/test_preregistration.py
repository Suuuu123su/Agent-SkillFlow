from pathlib import Path

import pytest
from pydantic import ValidationError

from skillflow.experiment.t16.preregistration import (
    load_preregistration,
    verify_scenario_bindings,
)
from skillflow.experiment.t16.preregistration_models import (
    IndependentFactor,
    SemanticInstanceSet,
    T16Intervention,
    T16Preregistration,
)
from skillflow.models.matrix_design import HiaaCell

PROJECT_ROOT = Path()
PREREGISTRATION = Path("experiments/t16/preregistration.yaml")


def test_preregistration_has_exact_closed_design_and_real_bindings() -> None:
    # Given: T16-A 的正式预注册文件。
    registration = load_preregistration(PREREGISTRATION)

    # When: 对 12 条件、实例和实际 Scenario/Manifest 进行复核。
    verify_scenario_bindings(registration, PROJECT_ROOT)

    # Then: 单模型矩阵严格为 12 x 10 x 3。
    assert registration.primary_trial_count == 360
    assert {item.condition_id for item in registration.conditions} == {
        "b0",
        "g0",
        "n0",
        "c1-p00",
        "c1-p01",
        "c1-p10",
        "c1-p11",
        "m2-control",
        "m2-target",
        "a1-claim",
        "a1-neutralized",
        "a2-structured-confirmation",
    }
    assert all(len(item.templates) == 10 for item in registration.instance_sets)


def test_c1_and_m2_bind_pre_registered_observations() -> None:
    # Given: 已解析的正式预注册。
    registration = load_preregistration(PREREGISTRATION)
    c1 = tuple(item for item in registration.conditions if item.hiaa_design_id is not None)
    m2 = tuple(item for item in registration.conditions if item.condition_id.startswith("m2-"))

    # When: 读取 HIAA 四格与撤销后观察点。
    cells = {item.hiaa_cell for item in c1}
    selectors = {item.harm_selector for item in c1}

    # Then: 四格共享同一个 selector，M2 只观察 Session 1 与 3。
    assert cells == set(HiaaCell)
    assert len(selectors) == 1
    assert all(item.observation_sessions == (1, 3) for item in m2)


def test_target_neutral_pair_rejects_data_format_drift() -> None:
    # Given: 一个已通过的正式设计。
    registration = load_preregistration(PREREGISTRATION)
    payload = registration.model_dump(mode="python")
    conditions = list(registration.conditions)
    target_index = next(
        index for index, item in enumerate(conditions) if item.condition_id == "m2-target"
    )
    target = conditions[target_index]
    changed_profile = target.capability.model_copy(update={"data_format": "application/json"})
    conditions[target_index] = target.model_copy(update={"capability": changed_profile})
    payload["conditions"] = conditions

    # When / Then: 除预注册自变量外的数据格式漂移必须被拒绝。
    with pytest.raises(ValidationError, match="格式或长度不匹配"):
        T16Preregistration.model_validate(payload)


def test_authorization_structure_only_changes_for_authorization_factor() -> None:
    # Given: 将授权组错误地声明成 Skill 语义自变量。
    registration = load_preregistration(PREREGISTRATION)
    payload = registration.model_dump(mode="python")
    changed = tuple(
        item.model_copy(update={"independent_factor": IndependentFactor.SKILL_SEMANTICS})
        if item.pair_group_id == "authorization-source"
        else item
        for item in registration.conditions
    )
    payload["conditions"] = changed

    # When / Then: 不同授权结构不再有例外，设计必须失败。
    with pytest.raises(ValidationError, match="相同授权结构"):
        T16Preregistration.model_validate(payload)


def test_semantic_instance_set_rejects_nine_templates() -> None:
    # Given: 正式实例集合中的前九条。
    registration = load_preregistration(PREREGISTRATION)
    templates = registration.instance_sets[0].templates[:-1]

    # When / Then: 少于十条不能进入实验。
    with pytest.raises(ValidationError):
        SemanticInstanceSet(instance_set_id="incomplete", templates=templates)


def test_authorization_neutralization_is_explicit_and_narrow() -> None:
    # Given: 三个授权条件。
    registration = load_preregistration(PREREGISTRATION)
    conditions = {item.condition_id: item for item in registration.conditions}

    # When / Then: 只有 A1 neutralized 删除授权声明。
    assert conditions["a1-neutralized"].intervention is (
        T16Intervention.NEUTRALIZE_AUTHORIZATION_CLAIM
    )
    assert conditions["a1-claim"].intervention is T16Intervention.NONE
    assert conditions["a2-structured-confirmation"].intervention is T16Intervention.NONE
