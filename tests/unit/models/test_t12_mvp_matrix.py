import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from skillflow.models.matrix import ExperimentMatrix
from skillflow.models.matrix_axes import (
    AuthorizationCondition,
    SessionCondition,
    SkillStateCondition,
)
from skillflow.validation import validate_yaml_document


def test_t12_mvp_matrix_has_twenty_four_controlled_core_variants() -> None:
    matrix = validate_yaml_document(Path("scenarios/matrix/mvp.yaml"), ExperimentMatrix)

    assert len(matrix.variants) == 24
    assert matrix.determinism_repeats == 5
    assert len(matrix.hiaa_designs) == 2
    assert all(
        sum(variant.hiaa_design_id == design.id for variant in matrix.variants) == 4
        for design in matrix.hiaa_designs
    )
    assert {variant.enforcement_mode.value for variant in matrix.variants} == {
        "monitor",
        "enforce",
    }
    assert {variant.provenance_mode.value for variant in matrix.variants} >= {
        "preserve",
        "drop_on_memory",
    }
    assert {variant.skill_state for variant in matrix.variants} == {
        SkillStateCondition.NORMAL,
        SkillStateCondition.REVOKED,
    }
    assert {variant.session_condition for variant in matrix.variants} == {
        SessionCondition.ORIGINAL,
        SessionCondition.NEW,
    }
    assert {variant.authorization_condition for variant in matrix.variants} >= {
        AuthorizationCondition.IMPLICIT_TEXT,
        AuthorizationCondition.STRUCTURED_CONFIRMATION,
    }
    assert len({variant.pair_id for variant in matrix.variants if variant.pair_id}) >= 6
    assert all(Path(variant.scenario.root).is_file() for variant in matrix.variants)
    assert all(Path(design.target_scenario.root).is_file() for design in matrix.hiaa_designs)
    assert all(Path(design.neutral_scenario.root).is_file() for design in matrix.hiaa_designs)


def test_t12_mvp_matrix_matches_static_json_schema() -> None:
    path = Path("scenarios/matrix/mvp.yaml")
    schema = json.loads(Path("schemas/experiment-matrix.schema.json").read_text(encoding="utf-8"))

    Draft202012Validator(schema).validate(yaml.safe_load(path.read_text(encoding="utf-8")))
