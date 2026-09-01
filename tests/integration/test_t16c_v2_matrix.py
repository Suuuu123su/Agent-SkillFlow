import hashlib
from pathlib import Path

from skillflow.experiment.t16.matrix import (
    load_matrix,
    validate_matrix_against_preregistration,
)
from skillflow.experiment.t16.preregistration import load_preregistration

ROOT = Path(__file__).parents[2]
T16_DIR = ROOT / "experiments" / "t16"
HISTORICAL_HASHES = {
    "preregistration.yaml": "4e2cf026bdeeb7901a47eb43fe8a38cf6ae5f2307960795360104cd6501779e1",
    "matrix_smoke.yaml": "8edc917d3c7b858f8aa73770d133905f145e01b9baf096ff507fea33287699a8",
    "matrix_model1.yaml": "3da730d691b3ace9f59cfded68ed09d18dca5e15031b3aa7a6fb9aae8eb719b6",
}


def test_t16c_v2_is_a_new_preregistration_and_keeps_v1_evidence_immutable() -> None:
    for name, expected_hash in HISTORICAL_HASHES.items():
        assert hashlib.sha256((T16_DIR / name).read_bytes()).hexdigest() == expected_hash

    registration = load_preregistration(T16_DIR / "preregistration_t16c_v2.yaml")
    matrices = tuple(
        load_matrix(T16_DIR / name)
        for name in (
            "matrix_smoke_t16c_v2.yaml",
            "matrix_model1_t16c_v2.yaml",
            "matrix_model2_subset_t16c_v2.yaml",
        )
    )

    assert registration.schema_version == "0.2"
    assert registration.id == "t16-live-llm-preregistration-v2"
    assert tuple(len(matrix.trials) for matrix in matrices) == (48, 360, 72)
    for matrix in matrices:
        validate_matrix_against_preregistration(matrix, registration)

    authorization_set = next(
        item
        for item in registration.instance_sets
        if item.instance_set_id == "authorization-prompts"
    )
    assert all("低可信" not in item.task_prompt for item in authorization_set.templates)
