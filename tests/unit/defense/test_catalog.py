from pathlib import Path

import pytest

from skillflow.experiment.t18.catalog import build_catalog
from skillflow.experiment.t18.controls import bind_matrix_controls
from skillflow.experiment.t18.matrix import build_matrix

ROOT = Path(__file__).resolve().parents[3]


def test_catalog_has_matched_pairs_and_real_hiaa_controls() -> None:
    catalog = build_catalog(ROOT, include_held_out=False)
    assert len(catalog.skills) == 20
    by_id = {s.skill_variant_id: s for s in catalog.skills}
    for base in ("C1", "C2"):
        a, n = (by_id[base.lower() + "-" + role] for role in ("attack", "neutral"))
        assert a.task_contract == n.task_contract
        assert a.task_plan == n.task_plan
        assert a.manifests == n.manifests
        assert a.scenario.grants == n.scenario.grants
        assert a.bundle != n.bundle or a.scenario.assets != n.scenario.assets
    controls = bind_matrix_controls(build_matrix("fake_reference"), catalog)
    assert len(controls) == 16
    assert len({c.shared_contract_sha256 for c in controls if c.design_id == "c1.monitor"}) == 1


def test_hiaa_changed_task_or_grant_is_not_reused() -> None:
    catalog = build_catalog(ROOT, include_held_out=False)
    skill = next(s for s in catalog.skills if s.skill_variant_id == "c1-neutral")
    changed = skill.model_copy(
        update={"scenario": skill.scenario.model_copy(update={"grants": ()})}
    )
    bad = catalog.model_copy(
        update={"skills": tuple(changed if s == skill else s for s in catalog.skills)}
    )
    with pytest.raises(ValueError, match="hiaa_shared"):
        bind_matrix_controls(build_matrix("fake_reference"), bad)


def test_catalog_neutral_roles_do_not_gain_grants() -> None:
    catalog = build_catalog(ROOT, include_held_out=False)
    skills = {s.skill_variant_id: s for s in catalog.skills}
    for base in ("b1", "c1", "c2", "m1", "m2", "a1", "s1", "l1"):
        assert skills[base + "-attack"].scenario.grants == skills[base + "-neutral"].scenario.grants
        assert skills[base + "-attack"].manifests == skills[base + "-neutral"].manifests
