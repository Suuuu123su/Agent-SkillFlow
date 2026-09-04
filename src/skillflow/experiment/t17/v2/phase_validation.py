"""不依赖宿主文件系统的阶段绑定核对，供标准数据集复算使用。"""

from skillflow.experiment.t17.v2.binding import validate_core_binding, validate_replay_binding
from skillflow.experiment.t17.v2.canonical import model_digest
from skillflow.experiment.t17.v2.loaded_models import LoadedStage
from skillflow.experiment.t17.v2.phase_gate import build_gate
from skillflow.experiment.t17.v2.phase_sources import phase_index
from skillflow.experiment.t17.v2.stage_contract import unit_identity
from skillflow.experiment.t17.v2.usage_validation import validate_usage


def validate_structured_stage(stage: LoadedStage) -> None:
    """数据集中的冻结调度、每个身份及每个实测投影都必须相符。"""
    result, matrix, config = stage.result, stage.matrix, stage.configuration
    phase = result.phase
    phases = phase_index(result)
    if (
        phase.configuration_sha256 != model_digest(config)
        or phase.matrix_sha256 != model_digest(matrix)
        or phase.catalog_sha256 != model_digest(config.catalog)
    ):
        raise ValueError("v2_dataset_phase_contract_binding")
    core_map = {c.identity.unit_id: c for c in result.cores}
    replay_map = {r.identity.unit_id: r for r in result.replays}
    if len(core_map) != len(result.cores) or len(replay_map) != len(result.replays):
        raise ValueError("v2_dataset_duplicate_terminal")
    if set(core_map) != {t.trial_id for t in matrix.trials} or set(replay_map) != {
        v for t in matrix.trials for v in t.replay_pair_ids.values()
    }:
        raise ValueError("v2_dataset_scheduled_units_mismatch")
    for trial in matrix.trials:
        core = core_map[trial.trial_id]
        source = phases.get(core.identity.phase_contract_sha256)
        if source is None or core.identity != unit_identity(source, matrix, trial, trial.trial_id):
            raise ValueError("v2_dataset_core_scheduled_identity")
        validate_core_binding(config, core)
        for alias, identifier in trial.replay_pair_ids.items():
            replay = replay_map[identifier]
            source = phases.get(replay.identity.phase_contract_sha256)
            if (
                source is None
                or replay.identity != unit_identity(source, matrix, trial, identifier)
                or replay.target_alias != alias
            ):
                raise ValueError("v2_dataset_replay_scheduled_identity")
            validate_replay_binding(core, replay)
    if result.gate != build_gate(
        phase, matrix, stage.group(), stage.api_usage, source_phases=result.source_phases
    ):
        raise ValueError("v2_dataset_recomputed_gate_drift")
    validate_usage(result, matrix, stage.api_usage)
