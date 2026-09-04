import pytest
from pydantic import ValidationError

from skillflow.experiment.t18.matrix import build_matrix


@pytest.mark.parametrize(
    ("domain", "expected"),
    [
        ("scripted", (228, 36, 36, 264, 18)),
        ("fake_reference", (32, 4, 12, 44, 4)),
    ],
)
def test_hiaa_expansion_is_deduplicated(
    domain: str, expected: tuple[int, int, int, int, int]
) -> None:
    original, reused, added, total, groups = expected
    matrix = build_matrix(domain)
    assert matrix.original_core_count == original
    assert matrix.reused_hiaa_cells == reused
    assert matrix.added_core_count == added
    assert len(matrix.cores) == total
    assert len({c.trial_id for c in matrix.cores}) == total
    assert len(matrix.hiaa_groups) == groups
    cells = {c.trial_id: c for c in matrix.cores}
    for group in matrix.hiaa_groups:
        assert set(group.cells) == {"p00", "p01", "p10", "p11"}
        quartet = [cells[group.cells[name]] for name in ("p00", "p01", "p10", "p11")]
        assert [(c.role, c.bridge_enabled) for c in quartet] == [
            ("neutral", False),
            ("neutral", True),
            ("attack", False),
            ("attack", True),
        ]
        assert len({c.seed for c in quartet}) == 1
        assert len({c.mode for c in quartet}) == 1
        assert len({c.semantic_instance for c in quartet}) == 1
        assert len({c.repeat for c in quartet}) == 1


def test_no_unknown_domain_or_silent_extra_repeats() -> None:
    with pytest.raises(ValueError, match="local_domain"):
        build_matrix("live")
    matrix = build_matrix("scripted")
    values = matrix.model_dump(mode="json")
    values["cores"][0]["repeat"] = 2
    with pytest.raises(ValidationError):
        type(matrix).model_validate(values)


def test_four_cell_omission_is_rejected() -> None:
    matrix = build_matrix("scripted")
    values = matrix.model_dump(mode="json")
    values["hiaa_groups"][0]["cells"].pop("p00")
    with pytest.raises(ValidationError, match="hiaa_four_cells"):
        type(matrix).model_validate(values)
