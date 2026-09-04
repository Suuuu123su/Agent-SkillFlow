"""保留两模型原合同，仅比较用户已批准的跨服务同任务矩阵。"""

# ruff: noqa: INP001

from typing import Literal

from skillflow.experiment.t17.live_matrix import T17LiveStage
from skillflow.experiment.t17.v2.canonical import model_digest
from skillflow.experiment.t17.v2.config_models import V2Configuration, V2Matrix
from skillflow.experiment.t17.v2.run_models import PhaseContract
from skillflow.models.base import StrictModel

PhaseInputs = tuple[V2Configuration, V2Matrix, PhaseContract]
_ALLOWED_RUNTIME_CHANGES = frozenset(
    "src/skillflow/experiment/t17/v2/" + name + ".py"
    for name in (
        "api_models",
        "binding",
        "dataset_io",
        "dataset_models",
        "dataset_reading",
        "gate_checks",
        "journal_order",
        "journal",
        "live_client",
        "network",
        "phase_gate",
        "phase_sources",
        "phase_validation",
        "replay_execution",
        "run_models",
        "usage_validation",
    )
)


class ModelPairContract(StrictModel):
    """各侧哈希原样登记，不为通过比较而重写已有配置或身份。"""

    schema_version: Literal["2.0"] = "2.0"
    left_configuration_sha256: str
    right_configuration_sha256: str
    left_matrix_sha256: str
    right_matrix_sha256: str
    left_phase_sha256: str
    right_phase_sha256: str
    configuration_differences: tuple[str, ...]
    runtime_differences: tuple[str, ...]
    scheduled_pairs: int
    replay_pairs_per_model: int
    shared_measurement_contract: Literal[True] = True
    pure_model_only_causal_comparison: Literal[False] = False
    pooling_allowed: Literal[False] = False
    limitations: tuple[str, ...] = (
        "比较的是用户批准的模型及服务配置组合，不单独识别模型权重的因果效应。",
        "DeepSeek 使用 system 角色；中等推理请求对应服务高档推理；控制正文不变。",
        "服务返回模型标识固定，但别名不是独立验证的不可变快照。",
        "零字节目标及完整用量的超限空响应采用用户批准修订，模型失败不补采。",
        "同模型网络失败按固定未完成序号续跑，全部失败费用另存，不按成功筛样。",
        (
            "G 第 13 个任务的整体耗时是本地恢复耗时；该平均值不用于线上速度排名，"
            "API 延迟仍来自原调用。"
        ),
    )


def validate_model_pair(left: PhaseInputs, right: PhaseInputs) -> ModelPairContract:
    """先逐项核对全部调度和测量合同，再允许分别计算两侧指标。"""
    lc, lm, lp = left
    rc, rm, rp = right
    for config, matrix, phase in (left, right):
        if (
            phase.configuration_sha256 != model_digest(config)
            or matrix.configuration_sha256 != model_digest(config)
            or phase.matrix_sha256 != model_digest(matrix)
            or phase.catalog_sha256 != model_digest(config.catalog)
            or matrix.catalog_sha256 != model_digest(config.catalog)
            or phase.domain != "live_reference"
            or phase.protocol_id != config.protocol_id
            or matrix.protocol_id != config.protocol_id
        ):
            raise ValueError("collection_source_contract_binding")
    if (
        lm.stage is not T17LiveStage.MODEL1
        or rm.stage is not T17LiveStage.MODEL2
        or lp.stage != lm.stage
        or rp.stage != rm.stage
        or lm.provider != lc.model1
        or rm.provider != rc.model2
        or lm.provider.model_id != "gpt-5.6-luna"
        or rm.provider.model_id != "deepseek-v4-flash"
        or lc.model_dump(exclude={"model2"}) != rc.model_dump(exclude={"model2"})
    ):
        raise ValueError("collection_unapproved_model_or_measurement_change")
    changed = tuple(
        sorted(
            name
            for name in set(lp.runtime_files) | set(rp.runtime_files)
            if lp.runtime_files.get(name) != rp.runtime_files.get(name)
        )
    )
    if not set(changed) <= _ALLOWED_RUNTIME_CHANGES:
        raise ValueError("collection_unapproved_runtime_change")
    if (lm.scheduled_core_trials, lm.scheduled_replay_pairs) != (360, 270) or (
        rm.scheduled_core_trials,
        rm.scheduled_replay_pairs,
    ) != (360, 270):
        raise ValueError("collection_formal_schedule_incomplete")
    if len(lm.trials) != len(rm.trials):
        raise ValueError("collection_trial_count_mismatch")
    for ltrial, rtrial in zip(lm.trials, rm.trials, strict=True):
        if ltrial.model_dump(exclude={"trial_id", "replay_pair_ids"}) != rtrial.model_dump(
            exclude={"trial_id", "replay_pair_ids"}
        ) or set(ltrial.replay_pair_ids) != set(rtrial.replay_pair_ids):
            raise ValueError("collection_trial_or_replay_design_mismatch")
    differences = tuple(
        field for field in V2Configuration.model_fields if getattr(lc, field) != getattr(rc, field)
    )
    return ModelPairContract(
        left_configuration_sha256=model_digest(lc),
        right_configuration_sha256=model_digest(rc),
        left_matrix_sha256=model_digest(lm),
        right_matrix_sha256=model_digest(rm),
        left_phase_sha256=model_digest(lp),
        right_phase_sha256=model_digest(rp),
        configuration_differences=differences,
        runtime_differences=changed,
        scheduled_pairs=len(lm.trials),
        replay_pairs_per_model=lm.scheduled_replay_pairs,
    )
