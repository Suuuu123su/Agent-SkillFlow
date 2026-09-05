from pathlib import Path

import pytest

from skillflow.experiment.t19.tasks import task_variant
from skillflow.oracle.errors import OracleInvariantError
from skillflow.oracle.state import OracleDataState
from skillflow.trace.contracts import ParentRelation

ROOT = Path(__file__).resolve().parents[3]


def test_derivation_cannot_backfill_missing_oracle_from_observed() -> None:
    state = OracleDataState("run", ())
    with pytest.raises(OracleInvariantError):
        state.record_derivation("only-observed-no-oracle", "derived")
    assert state.records == ()


def test_derivation_keeps_truth_parent_and_rejects_duplicate_identity() -> None:
    assets = task_variant(ROOT, "C2", "attack", "development").scenario.assets
    state = OracleDataState("run", assets)
    parent = state.records[0]
    state.record_derivation(parent.artifact_id, "derived")
    derived = state.require("derived")
    assert derived.gt_data == parent.gt_data
    assert derived.parents[0].parent_id == parent.artifact_id
    assert derived.parents[0].relation is ParentRelation.DERIVE
    with pytest.raises(OracleInvariantError):
        state.record_derivation(parent.artifact_id, "derived")
    assert state.require("derived") == derived
