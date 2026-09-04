"""运行前复核配置与源代码，并生成单元身份。"""

from pathlib import Path

from skillflow.experiment.t17.v2.canonical import model_digest
from skillflow.experiment.t17.v2.config_models import V2Configuration, V2Matrix, V2Trial
from skillflow.experiment.t17.v2.frozen import digest_files
from skillflow.experiment.t17.v2.matrix import build_matrix
from skillflow.experiment.t17.v2.run_models import PhaseContract, UnitIdentity, V2Domain


def freeze_phase(
    root: Path, config: V2Configuration, matrix: V2Matrix, domain: V2Domain
) -> PhaseContract:
    """拒绝未经目录生成的任务表，在任何请求之前绑定全部输入。"""
    if matrix != build_matrix(root, config, matrix.stage):
        raise ValueError("v2_matrix_configuration_drift")
    paths = {
        p.relative_to(root).as_posix()
        for p in (root / "src/skillflow").rglob("*.py")
        if p.relative_to(root).as_posix() != "src/skillflow/experiment/t17/protocol.py"
    }
    paths.add("src/skillflow/store/schema.sql")
    return PhaseContract(
        protocol_id=config.protocol_id,
        stage=matrix.stage,
        domain=domain,
        configuration_sha256=model_digest(config),
        matrix_sha256=model_digest(matrix),
        catalog_sha256=model_digest(config.catalog),
        runtime_files=digest_files(root, tuple(sorted(paths))),
        scheduled_core=matrix.scheduled_core_trials,
        scheduled_replay=matrix.scheduled_replay_pairs,
    )


def unit_identity(
    phase: PhaseContract, matrix: V2Matrix, trial: V2Trial, unit_id: str
) -> UnitIdentity:
    """身份只来自冻结任务表，模型无权提交。"""
    return UnitIdentity(
        protocol_id=phase.protocol_id,
        stage=phase.stage,
        domain=phase.domain,
        phase_contract_sha256=model_digest(phase),
        matrix_sha256=phase.matrix_sha256,
        unit_id=unit_id,
        trial_id=trial.trial_id,
        condition_id=trial.condition_id,
        source_variant=trial.source_variant,
        skill_variant_id=trial.skill_variant_id,
        skill_content_sha256=trial.skill_content_sha256,
        manifest_sha256=trial.manifest_sha256,
        task_contract_id=trial.task_contract_id,
        task_contract_sha256=trial.task_contract_sha256,
        semantic_template_id=trial.semantic_template_id,
        semantic_instance_id=trial.semantic_instance_id,
        repeat_index=trial.repeat_index,
        defense_base_id=trial.defense_base_id,
        enforcement_mode=trial.enforcement_mode,
        requested_model=matrix.provider.model_id,
        model_revision=matrix.provider.model_revision,
    )
