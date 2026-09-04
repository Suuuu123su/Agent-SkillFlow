"""正式费用入口只允许完整 T17；小矩阵仍可用于零费用软件验证。"""

from pathlib import Path

from skillflow.experiment.t17.live_matrix import T17LiveStage, load_live_preregistration
from skillflow.experiment.t17.v2.canonical import model_digest
from skillflow.experiment.t17.v2.config_models import V2Configuration, V2Matrix
from skillflow.models.matrix import ExperimentMatrix
from skillflow.validation import validate_yaml_document

_COUNTS = ((24, 18), (360, 270), (24, 18), (360, 270), (270, 270))
_TEMPLATE_COUNT = 5
_REPEAT_COUNT = 3


def require_full_t17(
    root: Path, configuration: V2Configuration, matrices: tuple[V2Matrix, ...]
) -> None:
    """固定五阶段、24 个条件、五种表述、三次重复及已登记模型。"""
    old = load_live_preregistration(root / "experiments/t17/preregistration.yaml")
    base = validate_yaml_document(root / "scenarios/matrix/mvp.yaml", ExperimentMatrix)
    if (
        len(configuration.templates) != _TEMPLATE_COUNT
        or configuration.repeats != _REPEAT_COUNT
        or configuration.templates != old.semantic_templates
        or configuration.model1 != old.model1_provider
        or configuration.model2 != old.model2_provider
        or tuple(item.configuration for item in configuration.catalog.conditions) != base.variants
        or tuple(matrix.stage for matrix in matrices) != tuple(T17LiveStage)
    ):
        raise ValueError("v2_formal_scope_configuration")
    for matrix, (core, replay) in zip(matrices, _COUNTS, strict=True):
        provider = (
            configuration.model2
            if matrix.stage in {T17LiveStage.MODEL2_CANARY, T17LiveStage.MODEL2}
            else configuration.model1
        )
        if (
            matrix.scheduled_core_trials != core
            or matrix.scheduled_replay_pairs != replay
            or len(matrix.trials) != core
            or sum(len(trial.replay_pair_ids) for trial in matrix.trials) != replay
            or matrix.configuration_sha256 != model_digest(configuration)
            or matrix.protocol_id != configuration.protocol_id
            or matrix.provider != provider
        ):
            raise ValueError("v2_formal_scope_matrix")
