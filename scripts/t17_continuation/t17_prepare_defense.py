"""用户允许 G/H 并行：F 通过后独立运行原预算内的 Luna H。"""

# ruff: noqa: T201

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from t17_replacement_models import ReplacementPlan

from skillflow.experiment.t17.live_matrix import T17LiveStage
from skillflow.experiment.t17.minimal.artifacts import write_checked_json
from skillflow.experiment.t17.v2.campaign_models import StageOutcome
from skillflow.experiment.t17.v2.config_models import V2Configuration
from skillflow.experiment.t17.v2.cost_models import BudgetApproval, CostPlan
from skillflow.experiment.t17.v2.cost_plan import stage_cost
from skillflow.experiment.t17.v2.frozen import file_digest
from skillflow.experiment.t17.v2.journal import read_journal
from skillflow.experiment.t17.v2.loading import read_model
from skillflow.experiment.t17.v2.matrix import build_matrix
from skillflow.experiment.t17.v2.static_protocol import freeze_protocol

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = "experiments/t17/v2-luna-defense-20260904"
OUTPUT = "runs/t17-v2-luna-defense-20260904-01"
PLAN = "docs/evidence/t17-v2-luna-defense-plan-20260904.json"
APPROVAL = "docs/evidence/t17-v2-luna-defense-approval-20260904.json"
G_PLAN = "docs/evidence/t17-v2-deepseek-empty-rule-plan-20260904.json"
F_OUTCOME = "runs/t17-v2-live-20260904-02/model1/attempt-01/stage-result.json"
F_USAGE = "runs/t17-v2-live-20260904-02/model1/attempt-01/raw/api-usage.jsonl"
DEFENSE_UNITS = 270


def prerequisite_paths() -> tuple[str, ...]:
    """H 的数据仅依赖 F，用户已经明确批准与 G 并行。"""
    result = read_model(ROOT / F_OUTCOME, StageOutcome)
    if result.status != "passed" or result.gate is None or not result.gate.passed:
        raise ValueError("defense_requires_completed_F")
    return (F_OUTCOME,)


def main() -> None:
    """从已批 F 配置和原 H 额度生成一次并行运行批准。"""
    prerequisites = prerequisite_paths()
    previous = read_model(ROOT / G_PLAN, ReplacementPlan)
    outcomes = tuple(
        read_model(p, StageOutcome)
        for p in (ROOT / previous.output).glob("*/attempt-*/stage-result.json")
    )
    f = read_model(ROOT / F_OUTCOME, StageOutcome)
    if f.status != "passed" or f.gate is None or not f.gate.passed:
        raise ValueError("defense_requires_completed_F")
    config = read_model(ROOT / "experiments/t17/v2/preregistration.json", V2Configuration)
    original = read_model(ROOT / "docs/evidence/t17-v2-cost-plan.json", CostPlan)
    planned = next(s for s in original.stages if s.stage is T17LiveStage.DEFENSE)
    if (
        config.model1.model_id != "gpt-5.6-luna"
        or planned.scheduled_core != DEFENSE_UNITS
        or planned.scheduled_replay != DEFENSE_UNITS
        or planned.budget.max_total_usd != Decimal("3.00")
    ):
        raise ValueError("defense_scope_or_budget_drift")
    historical_reserved = previous.historical_reserved_usd + sum(
        (o.usage.reserved_cost_usd for o in outcomes), Decimal(0)
    )
    remaining = previous.original_approved_usd - historical_reserved
    outstanding_g = max(
        Decimal(0),
        previous.allocated_usd - sum((o.usage.reserved_cost_usd for o in outcomes), Decimal(0)),
    )
    if planned.budget.max_total_usd + outstanding_g > remaining:
        raise ValueError("defense_original_budget_exhausted")
    samples = tuple(
        e.usage
        for e in read_journal(ROOT / F_USAGE)
        if e.event_type == "response" and e.usage is not None and e.model_revision == "gpt-5.6-luna"
    )
    estimate = stage_cost(
        ROOT, build_matrix(ROOT, config, T17LiveStage.DEFENSE), planned.budget, samples
    )
    plan = ReplacementPlan(
        protocol=PROTOCOL,
        output=OUTPUT,
        source_snapshot=previous.source_snapshot,
        historical_estimated_usd=previous.historical_estimated_usd
        + sum((o.usage.estimated_cost_usd for o in outcomes), Decimal(0)),
        historical_reserved_usd=historical_reserved,
        remaining_approved_usd=remaining,
        allocated_usd=planned.budget.max_total_usd,
        stages=(estimate,),
        model="gpt-5.6-luna",
        endpoint="https://api.openai.com/v1/responses",
        provider_effective_reasoning="medium",
        instruction_role="developer",
        usage_reference=F_USAGE,
        prerequisite_outcomes=prerequisites,
        parallel_with_second_model=True,
        parallel_unspent_stage_cap_usd=outstanding_g,
        model_version_limit="返回模型标识必须保持 gpt-5.6-luna，与 F 一致。",
        comparison_limit="H 与已通过 F 使用同一 Luna 配置，只改变监测／强制模式。",  # noqa: RUF001
        scope="只新增 H 的 270/270，与已完成 F 的 360/270 合为 630/540；不重跑 E/F。",
    )
    # 从原 F 配置建立 H 合同，未使用的旧 model2 字段不改写；只执行 defense。
    freeze_protocol(ROOT, ROOT / PROTOCOL, ROOT / "experiments/t17/v2/preregistration.json")
    write_checked_json(ROOT / PLAN, plan)
    write_checked_json(
        ROOT / APPROVAL,
        BudgetApproval(
            approval_id="t17-v2-luna-defense-20260904",
            cost_plan_sha256=file_digest(ROOT / PLAN).sha256,
            approved_at=datetime.now(UTC),
            approved_max_total_usd=plan.allocated_usd,
            user_explicit_approval=True,
            approval_basis=(
                "沿用用户已批准的完整 T17 58.25 美元总额及 H 3 美元阶段上限。"
                "第二模型替换为 DeepSeek 不改变 H 仅用 Luna、复用 F、只新增 270/270 的安排。"
                "全部旧 G、DeepSeek 失败及成功尝试费用已继续扣除，没有增加预算或实验条件。"
                "用户已同意重开 Luna 专用保钥窗口，并明确允许 G/H 并行。"
                "H 只要求 F 已通过；仍为未用完的 G 全部上限留出额度，双方不能重复分配余额。"
            ),
        ),
    )
    print(f"H_READY: 270/270; cap USD {plan.allocated_usd}; API=0", flush=True)


if __name__ == "__main__":
    main()
