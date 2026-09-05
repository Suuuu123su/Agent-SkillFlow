from pathlib import Path

import pytest

from skillflow.experiment.t17.v2.fake_client import V2FakeClient
from skillflow.experiment.t17.v2.run_models import UnitUsage
from skillflow.experiment.t19.execution import ExecutionSetup, execute
from skillflow.experiment.t19.replay import ReplaySetup, run_pair
from skillflow.experiment.t19.tasks import task_variant

from .test_t19_tasks import ScalarSourceClient

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("base", ["C1", "C2", "M2", "A1"])
def test_three_branches_use_actual_checkpoint_and_retained_budget(
    base: str, tmp_path: Path
) -> None:
    client = V2FakeClient()
    skill = task_variant(ROOT, base, "attack", "development")
    core, factory = execute(
        ExecutionSetup(ROOT, tmp_path / "core", "core", "fake_reference", "Monitor"),
        skill,
        client,
    )
    starts: list[tuple[str, int]] = []
    for cf in skill.scenario.counterfactuals:
        record = run_pair(
            ReplaySetup(
                ROOT,
                tmp_path / "replay",
                client,
                lambda name, steps: starts.append((name, steps)),
                UnitUsage,
            ),
            core,
            skill,
            factory,
            cf.target.alias,
        )
        assert record.status == "completed"
        assert record.proof is not None
        assert record.same_view is not None
        assert 0 < record.source_prefix_steps < 16
        assert len(record.branch_usage) == 3
        assert all(steps == record.source_prefix_steps for _, steps in starts[-3:])
        assert len({name for name, _ in starts[-3:]}) == 3


def test_absent_checkpoint_retains_source_evidence_without_branch_calls(tmp_path: Path) -> None:
    skill = task_variant(ROOT, "C1", "attack", "development")
    core, factory = execute(
        ExecutionSetup(ROOT, tmp_path / "core", "core", "scripted", "Monitor"),
        skill,
        None,
    )
    starts: list[str] = []
    record = run_pair(
        ReplaySetup(
            ROOT, tmp_path / "replay", None, lambda name, _: starts.append(name), UnitUsage
        ),
        core,
        skill,
        factory,
        "absent",
    )
    assert record.status == "not_applicable"
    assert record.absent_source == core.data.facts
    assert not starts


def test_source_outside_control_contract_does_not_start_paid_branches(tmp_path: Path) -> None:

    skill = task_variant(ROOT, "A1", "attack", "development")
    core, factory = execute(
        ExecutionSetup(ROOT, tmp_path / "core", "scalar", "fake_reference", "Monitor"),
        skill,
        ScalarSourceClient(),
    )
    starts: list[str] = []
    record = run_pair(
        ReplaySetup(
            ROOT,
            tmp_path / "replay",
            ScalarSourceClient(),
            lambda name, _: starts.append(name),
            UnitUsage,
        ),
        core,
        skill,
        factory,
        "authorization-claim",
    )
    assert record.status == "not_applicable"
    assert record.reason == "source_generation_outside_frozen_control_envelope"
    assert record.absent_source == core.data.facts
    assert not starts
