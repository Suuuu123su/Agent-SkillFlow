import pytest

from skillflow.models.matrix import ExperimentMatrix


def test_mvp_matrix_accepts_control_axes_and_five_determinism_repeats() -> None:
    # Given: 一个非 HIAA 核心变体，显式声明所有 T12 控制轴
    payload = {
        "schema_version": "0.1",
        "id": "t12-mvp",
        "determinism_repeats": 5,
        "variants": [
            {
                "variant": "b0-monitor-preserve",
                "scenario": "scenarios/benign/b0_legal_summary.yaml",
                "seed": 12,
                "pair_id": "pair-summary-authorization",
                "target_skill_present": False,
                "shared_context": True,
                "persistent_memory": False,
                "auto_approve_tools": False,
                "enforcement_mode": "monitor",
                "provenance_mode": "preserve",
                "implicit_text_authorization": False,
                "skill_state": "normal",
                "session_condition": "original",
                "authorization_condition": "structured_confirmation",
            }
        ],
    }

    # When: 解析 MVP Matrix
    matrix = ExperimentMatrix.model_validate(payload)

    # Then: 五次重复只作为矩阵计划，不制造五个核心变体
    assert matrix.determinism_repeats == 5
    assert len(matrix.variants) == 1
    assert matrix.variants[0].pair_id == "pair-summary-authorization"
    assert matrix.variants[0].skill_state.value == "normal"


def test_matrix_rejects_counterfactual_as_a_core_variant() -> None:
    # Given: 调用方试图把反事实分支塞进普通核心变体
    payload = {
        "schema_version": "0.1",
        "id": "t12-invalid",
        "determinism_repeats": 5,
        "variants": [
            {
                "variant": "bad-counterfactual",
                "scenario": "scenarios/attacks/a1_implicit_text_authorization.yaml",
                "seed": 12,
                "pair_id": "pair-text-authorization",
                "target_skill_present": True,
                "shared_context": True,
                "persistent_memory": False,
                "auto_approve_tools": False,
                "enforcement_mode": "monitor",
                "provenance_mode": "preserve",
                "implicit_text_authorization": True,
                "skill_state": "normal",
                "session_condition": "original",
                "authorization_condition": "implicit_text",
                "run_role": "counterfactual",
            }
        ],
    }

    # When/Then: Counterfactual 必须留在 Replay，不得成为普通分母候选
    with pytest.raises(ValueError, match="counterfactual"):
        ExperimentMatrix.model_validate(payload)
