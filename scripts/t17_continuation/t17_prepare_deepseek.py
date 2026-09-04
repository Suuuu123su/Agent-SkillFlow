"""机械生成 DeepSeek 的配置、两阶段提案和原总预算内的替换记录；零 API。"""

# ruff: noqa: T201

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from t17_replacement_models import ReplacementPlan

from skillflow.experiment.t16.provider import PricingRates, PricingStatus
from skillflow.experiment.t17.minimal.artifacts import write_checked_json
from skillflow.experiment.t17.v2.campaign_models import CampaignResult
from skillflow.experiment.t17.v2.config_models import V2Configuration
from skillflow.experiment.t17.v2.cost_models import BudgetApproval, CostPlan
from skillflow.experiment.t17.v2.cost_plan import stage_cost
from skillflow.experiment.t17.v2.frozen import file_digest
from skillflow.experiment.t17.v2.journal import read_journal
from skillflow.experiment.t17.v2.loading import read_model
from skillflow.experiment.t17.v2.matrix import build_matrix
from skillflow.experiment.t17.v2.static_protocol import freeze_protocol

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = "experiments/t17/v2-deepseek-20260904"
OUTPUT = "runs/t17-v2-deepseek-20260904-01"
PLAN = "docs/evidence/t17-v2-deepseek-budget-proposal-20260904.json"
APPROVAL = "docs/evidence/t17-v2-deepseek-budget-approval-20260904.json"
SNAPSHOT = "runs/t17-v2-live-20260904-02/campaign-after-attempt-007.json"


def main() -> None:
    """生成已批准的第二模型配置，原费用与任务合同保持不变。"""
    old = read_model(ROOT / "experiments/t17/v2/preregistration.json", V2Configuration)
    rates = PricingRates(
        status=PricingStatus.LIVE_PINNED,
        input_per_million_usd=Decimal("0.14"),
        cached_input_per_million_usd=Decimal("0.0028"),
        output_per_million_usd=Decimal("0.28"),
        reasoning_per_million_usd=Decimal("0.28"),
    )
    provider = old.model2.model_copy(
        update={
            "model_id": "deepseek-v4-flash",
            "model_revision": "deepseek-v4-flash",
            "pricing": rates,
        }
    )
    config = old.model_copy(update={"model2": provider})
    if config.model_dump(exclude={"model2"}) != old.model_dump(exclude={"model2"}):
        raise ValueError("replacement_non_model_configuration_changed")
    source = ROOT / ".tmp/t17-deepseek-20260904-01/deepseek-configuration.json"
    write_checked_json(source, config)
    freeze_protocol(ROOT, ROOT / PROTOCOL, source)
    previous = read_model(ROOT / SNAPSHOT, CampaignResult)
    old_plan = read_model(ROOT / "docs/evidence/t17-v2-cost-plan-restart-02.json", CostPlan)
    samples = tuple(
        e.usage
        for e in read_journal(
            ROOT / "runs/t17-v2-live-20260904-02/model1/attempt-01/raw/api-usage.jsonl"
        )
        if e.event_type == "response" and e.usage is not None
    )
    stages = []
    for old_stage, cap in zip(old_plan.stages[2:4], (Decimal(1), Decimal(5)), strict=True):
        budget = old_stage.budget.model_copy(update={"max_total_usd": cap})
        estimate = stage_cost(ROOT, build_matrix(ROOT, config, old_stage.stage), budget, samples)
        stages.append(
            estimate.model_copy(
                update={
                    "rate_source": "已有 DeepSeek 切换资料中的估算费率；本轮不重新核价",
                }
            )
        )
    historical_reserved = previous.reserved_cost_usd + Decimal("0.0028376")
    remaining = Decimal("58.25") - historical_reserved
    allocated = sum((s.budget.max_total_usd for s in stages), Decimal(0))
    if remaining != previous.remaining_approved_usd or allocated > remaining:
        raise ValueError("replacement_historical_budget_mismatch")
    plan = ReplacementPlan(
        protocol=PROTOCOL,
        output=OUTPUT,
        source_snapshot=SNAPSHOT,
        historical_estimated_usd=previous.estimated_cost_usd,
        historical_reserved_usd=historical_reserved,
        remaining_approved_usd=remaining,
        allocated_usd=allocated,
        stages=tuple(stages),
    )
    write_checked_json(ROOT / PLAN, plan)
    write_checked_json(
        ROOT / APPROVAL,
        BudgetApproval(
            approval_id="t17-v2-deepseek-replacement-20260904",
            cost_plan_sha256=file_digest(ROOT / PLAN).sha256,
            approved_at=datetime.now(UTC),
            approved_max_total_usd=allocated,
            user_explicit_approval=True,
            approval_basis=(
                "沿用用户已批准的 58.25 美元总额，并执行用户明确指示：第二模型改为 DeepSeek，"
                "已输入，用 dsv4flash；清理本轮 G 全部记录，保留 E/F 及费用。"
                "旧占用 14.9042924 美元不清零；从剩余 43.3457076 美元中仅分配 6 美元，"
                "预检 1 美元、正式 5 美元。不是新增预算，也不是允许扩大实验。"
            ),
        ),
    )
    print("READY: G precheck 24/18; formal 360/270; allocated USD 6; API=0")


if __name__ == "__main__":
    main()
