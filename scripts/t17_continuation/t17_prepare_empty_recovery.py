"""保留首次模型事实，仅另存经用户批准的零字节重放修正；零 API。"""

# ruff: noqa: T201

import shutil
from datetime import UTC, datetime
from pathlib import Path

from t17_continue_evidence import read_sources
from t17_continue_models import SourceIndex, source_unit, terminal_path
from t17_replacement_models import ReplacementPlan

from skillflow.experiment.t17.minimal.artifacts import write_checked_json
from skillflow.experiment.t17.v2.analysis_context import AnalysisGroup
from skillflow.experiment.t17.v2.binding import validate_replay_binding
from skillflow.experiment.t17.v2.campaign_models import StageOutcome
from skillflow.experiment.t17.v2.campaign_usage import journal_totals
from skillflow.experiment.t17.v2.cost_models import BudgetApproval
from skillflow.experiment.t17.v2.frozen import FrozenFile, file_digest, inside
from skillflow.experiment.t17.v2.loading import read_model
from skillflow.experiment.t17.v2.phase_gate import build_gate
from skillflow.experiment.t17.v2.phase_sources import phase_index
from skillflow.experiment.t17.v2.run_models import (
    CoreTerminal,
    PhaseContract,
    ReplayTerminal,
    StageResult,
)
from skillflow.experiment.t17.v2.stage_contract import freeze_phase
from skillflow.experiment.t17.v2.static_protocol import freeze_protocol, verify_protocol
from skillflow.experiment.t17.v2.unit_execution import compact_id
from skillflow.models.base import StrictModel

ROOT = Path(__file__).resolve().parents[2]
ORIGINAL_PLAN = "docs/evidence/t17-v2-deepseek-budget-proposal-20260904.json"
PLAN = "docs/evidence/t17-v2-deepseek-empty-rule-plan-20260904.json"
APPROVAL = "docs/evidence/t17-v2-deepseek-empty-rule-approval-20260904.json"
PROTOCOL = "experiments/t17/v2-deepseek-empty-rule-20260904"
CORRECTION = "runs/t17-v2-deepseek-20260904-01/empty-target-correction-01"
PRESERVED_RESPONSES = 3


class EmptyTargetCorrection(StrictModel):
    """记录用户批准及原失败到新重放终态的来源关系。"""

    user_confirmation: str
    reason: str = "target_empty_no_neutral_form"
    original_replay_path: str
    original_replay_file: FrozenFile
    corrected_replay_path: str
    corrected_replay_file: FrozenFile
    original_stage_result: str
    preserved_core_path: str
    source_phase: PhaseContract
    original_model_response_count: int = 3
    additional_model_requests: int = 0
    original_failure_kept: bool = True
    first_resumed_core_ordinal: int = 2


def main() -> None:
    """只生成一次空目标修订，不运行新的模型请求。"""
    plan = read_model(ROOT / ORIGINAL_PLAN, ReplacementPlan)
    first = inside(ROOT, plan.output) / "model2_canary/attempt-01"
    source = read_model(first / "selected-sources.json", SourceIndex)
    original_core = next(s for s in source.units if s.ordinal == 1 and s.kind == "core")
    original_replay = next(s for s in source.units if s.ordinal == 1 and s.kind == "replay")
    core = read_model(terminal_path(ROOT, original_core), CoreTerminal)
    failed = read_model(terminal_path(ROOT, original_replay), ReplayTerminal)
    outcome = read_model(first / "stage-result.json", StageOutcome)
    if failed.status != "protocol_error" or failed.reason != "HarnessStateError":
        raise ValueError("empty_recovery_unexpected_failure")
    if core.data is None or core.decisions[0].behavior != "schema_rejection":
        raise ValueError("empty_recovery_original_core_missing")
    corrected = failed.model_copy(
        update={
            "status": "not_applicable",
            "reason": "target_empty_no_neutral_form",
            "absent_source": core.data.facts,
        }
    )
    validate_replay_binding(core, corrected)
    target = inside(ROOT, CORRECTION)
    target.mkdir(parents=True, exist_ok=False)
    (target / "terminals").mkdir()
    source_phase = read_model(first / "raw/phase-contract.json", PhaseContract)
    write_checked_json(target / "phase-contract.json", source_phase)
    corrected_path = target / "terminals" / (compact_id(failed.identity.unit_id) + ".json")
    write_checked_json(corrected_path, corrected)
    # 同一份无正文用量日志另存引用；原日志及每个响应编号完全不变。
    shutil.copyfile(first / "raw/api-usage.jsonl", target / "api-usage.jsonl")
    replacement_source = source_unit(ROOT, target, 1, "replay", failed.identity.unit_id)
    selected = source.model_copy(
        update={
            "units": tuple(replacement_source if s == original_replay else s for s in source.units)
        }
    )
    selected_path = target / "selected-sources.json"
    write_checked_json(selected_path, selected)
    prefix = tuple(s for s in selected.units if s.ordinal == 1)
    cores, replays, events, _ = read_sources(ROOT, prefix)
    if cores != (core,) or replays != (corrected,):
        raise ValueError("empty_recovery_selected_source_changed")
    if not journal_totals(events).responses == outcome.usage.responses == PRESERVED_RESPONSES:
        raise ValueError("empty_recovery_response_count_changed")
    if journal_totals(events).estimated_cost_usd != outcome.usage.estimated_cost_usd:
        raise ValueError("empty_recovery_fee_changed")
    write_checked_json(
        target / "correction.json",
        EmptyTargetCorrection(
            user_confirmation="同意这一最小修订；保留模型失败及费用，不提高输出上限，不重采已有模型结果。",
            original_replay_path=terminal_path(ROOT, original_replay).relative_to(ROOT).as_posix(),
            original_replay_file=original_replay.terminal_file,
            corrected_replay_path=corrected_path.relative_to(ROOT).as_posix(),
            corrected_replay_file=file_digest(corrected_path),
            original_stage_result=(first / "stage-result.json").relative_to(ROOT).as_posix(),
            preserved_core_path=terminal_path(ROOT, original_core).relative_to(ROOT).as_posix(),
            source_phase=source_phase,
        ),
    )
    freeze_protocol(ROOT, ROOT / PROTOCOL, inside(ROOT, plan.protocol) / "preregistration.json")
    config, matrices = verify_protocol(ROOT, ROOT / PROTOCOL)
    matrix = matrices[2]
    phase = freeze_phase(ROOT, config, matrix, "live_reference")
    gate = build_gate(
        phase, matrix, AnalysisGroup(config, cores, replays), events, source_phases=(source_phase,)
    )
    phase_index(
        StageResult(
            phase=phase, source_phases=(source_phase,), cores=cores, replays=replays, gate=gate
        )
    )
    if not gate.usage_complete:
        raise ValueError("empty_recovery_usage_incomplete")
    amended = plan.model_copy(
        update={
            "protocol": PROTOCOL,
            "approved_prefix": selected_path.relative_to(ROOT).as_posix(),
        }
    )
    write_checked_json(ROOT / PLAN, amended)
    write_checked_json(
        ROOT / APPROVAL,
        BudgetApproval(
            approval_id="t17-v2-deepseek-empty-rule-20260904",
            cost_plan_sha256=file_digest(ROOT / PLAN).sha256,
            approved_at=datetime.now(UTC),
            approved_max_total_usd=plan.allocated_usd,
            user_explicit_approval=True,
            approval_basis=(
                "用户明确同意仅增加有零字节证明目标的重放不适用规则；保留模型失败和费用，"
                "不提高输出上限、不重采已有模型结果。本文件替换同一 G 的执行批准，不新增预算；"
                "原预检 1 美元、正式 5 美元上限不变，首轮 0.0010458168 美元继续累计。"
            ),
        ),
    )
    print("RECOVERY_READY: retained original core and all 3 responses; next core=2; API=0")


if __name__ == "__main__":
    main()
