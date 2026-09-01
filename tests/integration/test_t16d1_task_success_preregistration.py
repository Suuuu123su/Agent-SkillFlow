import hashlib
from decimal import Decimal
from pathlib import Path

from skillflow.experiment.t16.task_success_matrix import TaskSuccessSmokeMatrix
from skillflow.experiment.t16.task_success_prereg_models import (
    TaskSuccessPreregistrationV3,
)
from skillflow.experiment.t16.task_success_registration import (
    load_task_success_preregistration,
    load_task_success_registry,
    load_task_success_smoke_matrix,
    validate_task_success_matrix,
)
from skillflow.experiment.t16.task_success_spec_models import (
    TaskSuccessSpecificationRegistry,
)

ROOT = Path(__file__).parents[2]
T16_DIR = ROOT / "experiments" / "t16"
EXPECTED_CONDITIONS = {
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
EXPECTED_ASSERTION_TYPES = {
    "artifact_exists",
    "artifact_alias_resolves",
    "artifact_schema_valid",
    "artifact_structured_field_equals",
    "artifact_structured_set_equals",
    "artifact_content_commitment_matches",
    "required_receipt_exists",
    "receipt_bound_to_run",
    "receipt_bound_to_session",
    "safe_sink_commitment_matches",
    "required_session_reached",
    "required_tool_sequence_observed",
}
HISTORICAL_HASHES = {
    "experiments/t16/preregistration_t16c_v2.yaml": (
        "f12f6fe08e0055ebf749f16adc4c104f8cb8271bf3c7cf8202f1c01767a5b907"
    ),
    "experiments/t16/matrix_smoke_t16c_v2.yaml": (
        "e876392a07186f0c989ecfc1911a5f03a4fef11f48a8c37a1e5c76e7a1da0731"
    ),
    "experiments/t16/matrix_model1_t16c_v2.yaml": (
        "7efbcc31dc0d6792a80894e794b787bccd6f52de82df0c6c7e51fff276adb0b3"
    ),
    "experiments/t16/matrix_model2_subset_t16c_v2.yaml": (
        "302e171b4fad25b79cda6f78119d4de23270904536e998e82e6e97e74d5072f6"
    ),
    "runs/t16c-v2-live-20260829-01/attempt-01/smoke/trial-results.jsonl": (
        "89dcbc44ca4084ee41645f189df471353fbbbd99a7365c6346e8d99c058d6738"
    ),
    "runs/t16c-v2-live-20260829-01/attempt-01/model1/trial-results.jsonl": (
        "2538b342bff20799964392eac15f545c47e10f6f55e4c56c315b1a85d3618f04"
    ),
    "docs/evidence/t16c-v2-live-reanalysis-v0.4-20260829.json": (
        "325c2ab7231f0773a99f1ac55c8a087e07aa92259b72ed70a0a5e63ae2f24c8a"
    ),
}


def _load_all() -> tuple[
    TaskSuccessSpecificationRegistry,
    TaskSuccessPreregistrationV3,
    TaskSuccessSmokeMatrix,
]:
    registry = load_task_success_registry(T16_DIR / "task_success_assertions_v3.yaml")
    preregistration = load_task_success_preregistration(
        T16_DIR / "preregistration_task_success_v3.yaml"
    )
    matrix = load_task_success_smoke_matrix(T16_DIR / "matrix_task_success_smoke_v3.yaml")
    return registry, preregistration, matrix


def test_v3_freezes_all_conditions_assertions_and_bridge_boundary() -> None:
    registry, preregistration, matrix = _load_all()

    assert {item.condition_id for item in registry.conditions} == EXPECTED_CONDITIONS
    assert {
        assertion.assertion_type.value
        for item in registry.conditions
        for assertion in item.assertions
    } == EXPECTED_ASSERTION_TYPES
    assert preregistration.study_role == "bridge_calibration"
    assert preregistration.prompt_contract.version == "3.0"
    assert preregistration.prompt_contract.old_v2_mergeable is False
    assert preregistration.task_success_specification_id == registry.id
    validate_task_success_matrix(matrix, preregistration, registry)


def test_v3_smoke_is_48_offline_locked_trials_with_three_dollar_cap() -> None:
    registry, preregistration, matrix = _load_all()

    assert len(matrix.trials) == 48
    assert len({item.trial_id for item in matrix.trials}) == 48
    assert {item.repeat_index for item in matrix.trials} == {1, 2}
    assert len({item.semantic_instance_id for item in matrix.trials}) == 10
    assert matrix.budget.allow_live is False
    assert matrix.budget.max_total_usd == Decimal("3.00")
    assert matrix.provider.kind.value == "live"
    assert matrix.provider.pricing.status.value == "live_pending"
    assert matrix.preregistration_id == preregistration.id
    assert {item.task_success_spec_id for item in matrix.trials} == {
        item.spec_id for item in registry.conditions
    }


def test_v3_pairing_hiaa_sessions_and_output_contracts_are_matched() -> None:
    registry, preregistration, matrix = _load_all()
    by_condition = {item.condition_id: item for item in preregistration.conditions}
    spec_by_condition = {item.condition_id: item for item in registry.conditions}

    for pair in (
        ("c1-p00", "c1-p10"),
        ("c1-p01", "c1-p11"),
        ("m2-control", "m2-target"),
        ("a1-claim", "a1-neutralized"),
    ):
        left, right = (by_condition[item] for item in pair)
        assert left.task_output_contract_id == right.task_output_contract_id
        assert spec_by_condition[pair[0]].contract_fingerprint == (
            spec_by_condition[pair[1]].contract_fingerprint
        )
        left_pairs = {item.pair_id for item in matrix.trials if item.condition_id == pair[0]}
        right_pairs = {item.pair_id for item in matrix.trials if item.condition_id == pair[1]}
        assert left_pairs == right_pairs

    c1 = [by_condition[item] for item in sorted(EXPECTED_CONDITIONS) if item.startswith("c1-")]
    assert len({item.harm_selector for item in c1}) == 1
    assert {item.hiaa_cell.value for item in c1} == {"p00", "p01", "p10", "p11"}
    assert by_condition["m2-control"].observation_sessions == (1, 3)
    assert by_condition["m2-target"].observation_sessions == (1, 3)


def test_task_success_assertions_exclude_dangerous_effects() -> None:
    registry, _, _ = _load_all()
    for specification in registry.conditions:
        assertion_effect_aliases = {
            assertion.effect_alias
            for assertion in specification.assertions
            if hasattr(assertion, "effect_alias")
        }
        assert assertion_effect_aliases.isdisjoint(specification.dangerous_effect_aliases_excluded)


def test_old_v2_evidence_hashes_remain_byte_identical() -> None:
    for relative_path, expected in HISTORICAL_HASHES.items():
        assert hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest() == expected
