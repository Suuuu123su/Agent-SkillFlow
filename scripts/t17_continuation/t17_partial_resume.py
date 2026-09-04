"""网络中断后只恢复断点索引；不把缺失响应用量的原尝试改为通过。"""

from pathlib import Path

from t17_continue_models import ContinuationPlan, SourceIndex, source_unit
from t17_replacement_models import ReplacementPlan

from skillflow.experiment.t17.minimal.artifacts import write_checked_json
from skillflow.experiment.t17.v2.campaign_models import StageOutcome
from skillflow.experiment.t17.v2.config_models import V2Matrix
from skillflow.experiment.t17.v2.loading import read_model
from skillflow.experiment.t17.v2.run_models import PhaseContract, PhaseGate


def recover_partial_index(
    root: Path, directory: Path, outcome: StageOutcome, plan: ReplacementPlan
) -> StageOutcome:
    """完整验证器拒绝不完整用量是正确的；续跑应读取失败阶段门和完好前缀。"""
    raw = directory / "raw"
    if (
        outcome.gate is not None
        or outcome.reason != "ValueError"
        or outcome.usage.complete
        or outcome.usage.missing_reason
        not in {
            "network_response_state_unknown",
            "timeout",
            "provider_error",
        }
        or not (raw / "phase-gate.json").is_file()
    ):
        return outcome
    gate = read_model(raw / "phase-gate.json", PhaseGate)
    matrix = read_model(raw / "matrix.json", V2Matrix)
    phase = read_model(raw / "phase-contract.json", PhaseContract)
    expected = next(s for s in plan.stages if s.stage == outcome.stage)
    if (
        gate.passed
        or not gate.infrastructure_invalid
        or gate.protocol_errors
        or gate.binding_failures
        or phase.matrix_sha256 != expected.matrix_sha256
        or matrix.provider.model_id != plan.model
        or matrix.stage != outcome.stage
    ):
        return outcome
    path = directory / "selected-sources.json"
    if not path.exists():
        units = []
        for ordinal, trial in enumerate(matrix.trials, 1):
            units.append(source_unit(root, raw, ordinal, "core", trial.trial_id))
            units.extend(
                source_unit(root, raw, ordinal, "replay", value)
                for value in trial.replay_pair_ids.values()
            )
        selection = SourceIndex(
            plan=ContinuationPlan(
                source_raw=raw.relative_to(root).as_posix(),
                output_relative_path=directory.relative_to(root).as_posix(),
                snapshot_relative_path=plan.source_snapshot,
                first_ordinal=1,
                first_trial_id=matrix.trials[0].trial_id,
                user_instruction="网络中断从首个未完成任务组续跑；不完整尝试和未知用量保留。",
            ),
            units=tuple(units),
        )
        write_checked_json(path, selection)
    # 仅内存中补充实际已保存的失败阶段门，费用和原 stage-result.json 不改写。
    return outcome.model_copy(update={"gate": gate})
