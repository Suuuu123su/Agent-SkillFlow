from pathlib import Path

from skillflow.experiment.t17.live_matrix import (
    T17LiveStage,
    build_live_matrix,
    load_live_matrix,
    load_live_preregistration,
)
from skillflow.experiment.t17.scenario_registry import (
    load_scenario_measurement_registry,
)


def test_t17_live_matrices_have_frozen_core_and_replay_counts() -> None:
    # Given: the T17 preregistration and 16-scenario measurement registry.
    registration = load_live_preregistration(Path("experiments/t17/preregistration.yaml"))
    registry = load_scenario_measurement_registry(
        Path("experiments/t17/scenario_measurements.yaml")
    )

    # When: Canary, Model1 and Model2 matrices are mechanically expanded.
    canary = build_live_matrix(Path(), registration, registry, T17LiveStage.CANARY)
    model1 = build_live_matrix(Path(), registration, registry, T17LiveStage.MODEL1)
    model2_canary = build_live_matrix(
        Path(),
        registration,
        registry,
        T17LiveStage.MODEL2_CANARY,
    )
    model2 = build_live_matrix(Path(), registration, registry, T17LiveStage.MODEL2)
    defense = build_live_matrix(
        Path(),
        registration,
        registry,
        T17LiveStage.DEFENSE,
    )

    # Then: the exact plan counts, models and unique Trial identities are frozen.
    assert (canary.scheduled_core_trials, canary.scheduled_replay_pairs) == (24, 18)
    assert (model1.scheduled_core_trials, model1.scheduled_replay_pairs) == (360, 270)
    assert (
        model2_canary.scheduled_core_trials,
        model2_canary.scheduled_replay_pairs,
    ) == (24, 18)
    assert (model2.scheduled_core_trials, model2.scheduled_replay_pairs) == (360, 270)
    assert (defense.scheduled_core_trials, defense.scheduled_replay_pairs) == (
        270,
        270,
    )
    assert model1.provider.model_id == "gpt-5.6-luna"
    assert model2.provider.model_id == "gpt-5.5-2026-04-23"
    assert defense.provider.model_id == "gpt-5.6-luna"
    assert canary.budget.max_total_usd < model1.budget.max_total_usd
    assert model2_canary.budget.max_total_usd < model2.budget.max_total_usd
    assert len({item.trial_id for item in model1.trials}) == 360
    assert {item.repeat_index for item in model1.trials} == {1, 2, 3}
    assert len({item.variant for item in defense.trials}) == 18
    assert len({item.source_variant for item in defense.trials}) == 18
    assert all(item.variant != item.source_variant for item in defense.trials)
    assert {len(item.replay_target_aliases) for item in defense.trials} == {0, 1, 2}
    assert sum(len(item.replay_target_aliases) for item in defense.trials) == 270


def test_t17_checked_in_live_matrices_equal_mechanical_expansion() -> None:
    # Given: the same preregistration and registry used by the generator.
    registration = load_live_preregistration(Path("experiments/t17/preregistration.yaml"))
    registry = load_scenario_measurement_registry(
        Path("experiments/t17/scenario_measurements.yaml")
    )
    paths = {
        T17LiveStage.CANARY: Path("experiments/t17/matrix_canary.yaml"),
        T17LiveStage.MODEL1: Path("experiments/t17/matrix_model1.yaml"),
        T17LiveStage.MODEL2_CANARY: Path("experiments/t17/matrix_model2_canary.yaml"),
        T17LiveStage.MODEL2: Path("experiments/t17/matrix_model2.yaml"),
        T17LiveStage.DEFENSE: Path("experiments/t17/matrix_defense.yaml"),
    }

    # When/Then: every checked-in Matrix equals its generated value exactly.
    for stage, path in paths.items():
        assert load_live_matrix(path) == build_live_matrix(
            Path(),
            registration,
            registry,
            stage,
        )
