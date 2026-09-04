"""跨服务汇总只允许已批准模型差异，不能改写原任务或阶段身份。"""

from pathlib import Path

import pytest

from skillflow.experiment.t17.v2.config_models import V2Configuration, V2Matrix
from skillflow.experiment.t17.v2.loading import read_model
from skillflow.experiment.t17.v2.run_models import PhaseContract

ROOT = Path(__file__).resolve().parents[4]


def inputs() -> tuple[tuple[V2Configuration, V2Matrix, PhaseContract], ...]:
    folders = ("v2", "v2-deepseek-output-rule-20260904")
    stages = ("model1", "model2")
    return tuple(
        (
            read_model(ROOT / "experiments/t17" / folder / "preregistration.json", V2Configuration),
            read_model(ROOT / "experiments/t17" / folder / f"matrix-{stage}.json", V2Matrix),
            read_model(ROOT / "experiments/t17" / folder / f"phase-{stage}.json", PhaseContract),
        )
        for folder, stage in zip(folders, stages, strict=True)
    )


def test_approved_model_switch_preserves_full_matrix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.syspath_prepend(str(ROOT / "scripts/t17_delivery"))
    from t17_collection_binding import validate_model_pair  # noqa: PLC0415

    left, right = inputs()
    result = validate_model_pair(left, right)
    assert result.scheduled_pairs == 360
    assert result.replay_pairs_per_model == 270
    assert result.configuration_differences == ("model2",)
    assert result.shared_measurement_contract
    assert not result.pure_model_only_causal_comparison


def test_changed_prompt_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.syspath_prepend(str(ROOT / "scripts/t17_delivery"))
    from t17_collection_binding import validate_model_pair  # noqa: PLC0415

    left, right = inputs()
    config, matrix, phase = right
    changed = matrix.trials[0].model_copy(update={"task_prompt": "changed"})
    matrix = matrix.model_copy(update={"trials": (changed, *matrix.trials[1:])})
    with pytest.raises(ValueError, match="collection_source_contract_binding"):
        validate_model_pair(left, (config, matrix, phase))


def test_changed_statistical_contract_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.syspath_prepend(str(ROOT / "scripts/t17_delivery"))
    from t17_collection_binding import validate_model_pair  # noqa: PLC0415

    left, right = inputs()
    config, matrix, phase = right
    config = config.model_copy(update={"repeats": 4})
    with pytest.raises(ValueError, match="collection_source_contract_binding"):
        validate_model_pair(left, (config, matrix, phase))
