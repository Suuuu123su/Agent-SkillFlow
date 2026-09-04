"""用户批准的空目标和完整用量超限修复保留源阶段身份，不重采模型结果。"""

from skillflow.experiment.t17.v2.canonical import model_digest
from skillflow.experiment.t17.v2.run_models import PhaseContract, StageResult

# 只允许获准判定及来源保存模块变化，不允许任务、提示或模型选择变化。
_AMENDMENT_FILES = frozenset(
    "src/skillflow/experiment/t17/v2/" + name + ".py"
    for name in (
        "replay_execution",
        "binding",
        "run_models",
        "phase_sources",
        "phase_gate",
        "gate_checks",
        "phase_validation",
        "usage_validation",
        "journal",
        "journal_order",
        "dataset_models",
        "dataset_io",
        "dataset_reading",
    )
)


def phase_index(result: StageResult) -> dict[str, PhaseContract]:
    """来源阶段须保留相同任务表、模型配置、统计及执行域。"""
    current = result.phase
    phases = {model_digest(current): current}
    for source in result.source_phases:
        if current.stage.value not in {"model2_canary", "model2"} or current.model_dump(
            exclude={"runtime_files"}
        ) != source.model_dump(exclude={"runtime_files"}):
            raise ValueError("v2_source_phase_contract_mismatch")
        changed = {
            name
            for name in set(current.runtime_files) | set(source.runtime_files)
            if current.runtime_files.get(name) != source.runtime_files.get(name)
        }
        allowed = _AMENDMENT_FILES
        if current.stage.value == "model2":
            allowed |= {"src/skillflow/experiment/t17/v2/live_client.py"}
        if not changed <= allowed:
            raise ValueError("v2_source_phase_runtime_change_not_approved")
        digest = model_digest(source)
        if digest in phases:
            raise ValueError("v2_duplicate_source_phase")
        phases[digest] = source
    return phases
