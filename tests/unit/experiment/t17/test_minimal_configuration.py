from pathlib import Path

import pytest

from skillflow.experiment.t17.minimal.configuration import build_minimal_configuration


def test_minimal_configuration_preserves_pairs_and_only_needed_replays() -> None:
    config = build_minimal_configuration(Path())
    assert len(config.matrix.variants) == 23
    assert config.expected_replay_pairs == 12
    assert config.semantic_instances == config.primary_repeats == 1
    assert len(config.tasks) == 16
    variants = {item.variant for item in config.matrix.variants}
    assert {"s1-control", "b0-monitor", "b0-enforce", "b1-monitor", "b1-enforce"} <= variants
    assert not {"s1-enforce", "g0-drop-memory"} & variants
    assert len(config.replay_variants) == 10
    assert config.matrix.determinism_repeats == 1


def test_normal_task_contract_is_separate_from_attack_golden() -> None:
    tasks = {item.scenario_id: item for item in build_minimal_configuration(Path()).tasks}
    assert tasks["C1"].artifacts == tasks["N0"].artifacts
    assert tasks["C1"].effects == tasks["N0"].effects == ()
    assert tasks["C2"].effects == tasks["C2_CONTROL"].effects
    assert len(tasks["C2"].effects) == 1
    assert tasks["C2"].effects[0].selector.action.value == "file.read"
    assert tasks["B1"].effects == tasks["B0"].effects
    assert len(tasks["B1"].effects) == 1
    assert tasks["A1"].effects == ()
    assert len(tasks["A2"].effects) == 1
    assert tasks["M1"].effects == ()
    assert len(tasks["G0"].effects) == 1
    assert {item.alias for item in tasks["M2"].artifacts} == {"m2-memory-1", "m2-memory-3"}
    assert tasks["S1"].artifacts == tasks["S1_CONTROL"].artifacts
    assert tasks["S1"].effects == tasks["S1_CONTROL"].effects
    assert tasks["L1"].effects[0].session_id == "session-0"


def test_configuration_is_deterministic_and_forbids_schedule_drift() -> None:
    first = build_minimal_configuration(Path())
    second = build_minimal_configuration(Path())
    assert first == second
    document = first.model_dump(mode="json")
    document["expected_replay_pairs"] = 13
    with pytest.raises(ValueError, match="replay"):
        type(first).model_validate(document)
    document = first.model_dump(mode="json")
    document["tasks"][0]["effects"] = []
    with pytest.raises(ValueError, match=r"paired|task|contract"):
        type(first).model_validate(document)
