"""目录、正式分母与跨模型相同条件的机械生成。"""

from pathlib import Path

import pytest

from skillflow.experiment.t17.live_matrix import T17LiveStage
from skillflow.experiment.t17.v2.config_models import V2Configuration, V2Trial
from skillflow.experiment.t17.v2.configuration import build_configuration, write_configuration
from skillflow.experiment.t17.v2.matrix import build_matrix, verify_catalog_inputs


@pytest.fixture(scope="module")
def config(t17_cli_root: Path) -> V2Configuration:
    root = Path.cwd()
    destination = t17_cli_root / "v2-inputs"
    configuration, bundles = build_configuration(root, destination)
    write_configuration(root, destination, configuration, bundles)
    return configuration


@pytest.mark.parametrize(
    ("stage", "core", "replay"),
    [
        (T17LiveStage.CANARY, 24, 18),
        (T17LiveStage.MODEL1, 360, 270),
        (T17LiveStage.MODEL2_CANARY, 24, 18),
        (T17LiveStage.MODEL2, 360, 270),
        (T17LiveStage.DEFENSE, 270, 270),
    ],
)
def test_exact_full_stage_counts(
    config: V2Configuration, stage: T17LiveStage, core: int, replay: int
) -> None:
    matrix = build_matrix(Path.cwd(), config, stage)
    assert matrix.scheduled_core_trials == core
    assert matrix.scheduled_replay_pairs == replay
    assert len({item.trial_id for item in matrix.trials}) == core
    assert len({pair for item in matrix.trials for pair in item.replay_pair_ids.values()}) == replay
    assert all(item.skill_content_sha256 and item.task_contract_sha256 for item in matrix.trials)


def test_models_share_conditions_and_defense_is_disjoint_complement(
    config: V2Configuration,
) -> None:
    root = Path.cwd()
    a = build_matrix(root, config, T17LiveStage.MODEL1)
    b = build_matrix(root, config, T17LiveStage.MODEL2)
    defense = build_matrix(root, config, T17LiveStage.DEFENSE)
    fields = {"trial_id", "replay_pair_ids"}
    assert [t.model_dump(exclude=fields) for t in a.trials] == [
        t.model_dump(exclude=fields) for t in b.trials
    ]

    def key(trial: V2Trial) -> tuple[str, str, int, str]:
        return (
            trial.defense_base_id,
            trial.semantic_template_id,
            trial.repeat_index,
            trial.enforcement_mode,
        )

    assert not {key(t) for t in a.trials} & {key(t) for t in defense.trials}
    assert len({key(t) for t in (*a.trials, *defense.trials)}) == 630


def test_runtime_rechecks_actual_skill_and_manifest_bytes(config: V2Configuration) -> None:
    verify_catalog_inputs(Path.cwd(), config)
    entry = config.catalog.variants[0].model_copy(update={"skill_content_sha256": "0" * 64})
    catalog = config.catalog.model_copy(update={"variants": (entry, *config.catalog.variants[1:])})
    bad = config.model_copy(update={"catalog": catalog})
    with pytest.raises(ValueError, match="skill_content_drift"):
        verify_catalog_inputs(Path.cwd(), bad)
