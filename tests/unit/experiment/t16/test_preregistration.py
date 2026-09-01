from pathlib import Path

import pytest
from pydantic import ValidationError

from skillflow.experiment.t16 import preregistration as preregistration_module
from skillflow.experiment.t16.preregistration import (
    PreregistrationBindingError,
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
from skillflow.models.scenario import Scenario

PROJECT_ROOT = Path()
PREREGISTRATION = Path("experiments/t16/preregistration.yaml")
LIVE_PREREGISTRATION = Path("experiments/t16/preregistration_t16c_v2.yaml")


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


def test_live_c1_hiaa_keeps_identical_payload_across_all_four_cells() -> None:
    registration = load_preregistration(LIVE_PREREGISTRATION)
    c1 = tuple(item for item in registration.conditions if item.hiaa_design_id is not None)

    assert {item.capability.payload for item in c1} == {'{"send":"yes"}'}


def test_hiaa_rejects_payload_as_an_unregistered_third_factor() -> None:
    registration = load_preregistration(LIVE_PREREGISTRATION)
    payload = registration.model_dump(mode="python")
    conditions = list(registration.conditions)
    index = next(
        position for position, item in enumerate(conditions) if item.condition_id == "c1-p00"
    )
    condition = conditions[index]
    conditions[index] = condition.model_copy(
        update={"capability": condition.capability.model_copy(update={"payload": '{"send":"no "}'})}
    )
    payload["conditions"] = conditions

    with pytest.raises(ValidationError, match="相同输入 payload"):
        T16Preregistration.model_validate(payload)


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


def test_binding_rejects_same_authorization_structure_id_with_different_real_grants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registration = load_preregistration(LIVE_PREREGISTRATION)
    original_validate = preregistration_module.validate_yaml_document
    target_path = Path("scenarios/attacks/m2_revoked_memory_residual.yaml")

    def drifted_document(path: Path, model: type[object]) -> object:
        document = original_validate(path, model)
        if model is Scenario and path == target_path:
            assert isinstance(document, Scenario)
            return document.model_copy(update={"grants": document.grants[:-1]})
        return document

    monkeypatch.setattr(preregistration_module, "validate_yaml_document", drifted_document)

    with pytest.raises(PreregistrationBindingError, match=r"Grant.*结构 ID"):
        verify_scenario_bindings(registration, PROJECT_ROOT)


def test_binding_rejects_harm_selector_missing_from_real_scenario(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registration = load_preregistration(LIVE_PREREGISTRATION)
    original_validate = preregistration_module.validate_yaml_document
    target_path = Path("scenarios/attacks/c1_context_composition.yaml")

    def drifted_document(path: Path, model: type[object]) -> object:
        document = original_validate(path, model)
        if model is Scenario and path == target_path:
            assert isinstance(document, Scenario)
            return document.model_copy(update={"effect_selectors": ()})
        return document

    monkeypatch.setattr(preregistration_module, "validate_yaml_document", drifted_document)

    with pytest.raises(PreregistrationBindingError, match="harm_selector"):
        verify_scenario_bindings(registration, PROJECT_ROOT)


def test_binding_rejects_observation_session_outside_real_scenario() -> None:
    registration = load_preregistration(LIVE_PREREGISTRATION)
    conditions = tuple(
        item.model_copy(update={"observation_sessions": (1, 4)})
        if item.condition_id == "m2-target"
        else item
        for item in registration.conditions
    )
    drifted = registration.model_copy(update={"conditions": conditions})

    with pytest.raises(PreregistrationBindingError, match="观察 Session"):
        verify_scenario_bindings(drifted, PROJECT_ROOT)


def test_binding_rejects_observation_session_id_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registration = load_preregistration(LIVE_PREREGISTRATION)
    original_validate = preregistration_module.validate_yaml_document
    target_path = Path("scenarios/attacks/m2_revoked_memory_residual.yaml")

    def drifted_document(path: Path, model: type[object]) -> object:
        document = original_validate(path, model)
        if model is Scenario and path == target_path:
            assert isinstance(document, Scenario)
            sessions = tuple(
                session.model_copy(update={"id": "renamed-observation"}) if index == 1 else session
                for index, session in enumerate(document.sessions)
            )
            return document.model_copy(update={"sessions": sessions})
        return document

    monkeypatch.setattr(preregistration_module, "validate_yaml_document", drifted_document)

    with pytest.raises(PreregistrationBindingError, match=r"session\.id"):
        verify_scenario_bindings(registration, PROJECT_ROOT)


def test_binding_rejects_harness_drift_within_a_matched_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registration = load_preregistration(LIVE_PREREGISTRATION)
    original_validate = preregistration_module.validate_yaml_document
    target_path = Path("scenarios/attacks/m2_revoked_memory_residual.yaml")

    def drifted_document(path: Path, model: type[object]) -> object:
        document = original_validate(path, model)
        if model is Scenario and path == target_path:
            assert isinstance(document, Scenario)
            harness = document.harness.model_copy(update={"persistent_memory": False})
            return document.model_copy(update={"harness": harness})
        return document

    monkeypatch.setattr(preregistration_module, "validate_yaml_document", drifted_document)

    with pytest.raises(PreregistrationBindingError, match="Harness"):
        verify_scenario_bindings(registration, PROJECT_ROOT)
