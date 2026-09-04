"""冻结获准的完整用量超限修复，保留 G 的原响应，仍只分配原 6 美元。"""

# ruff: noqa: T201

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from t17_replacement_models import ReplacementPlan

from skillflow.experiment.t17.minimal.artifacts import write_checked_json
from skillflow.experiment.t17.v2.campaign_models import StageOutcome
from skillflow.experiment.t17.v2.cost_models import BudgetApproval
from skillflow.experiment.t17.v2.frozen import file_digest
from skillflow.experiment.t17.v2.loading import read_model
from skillflow.experiment.t17.v2.static_protocol import freeze_protocol

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = "experiments/t17/v2-deepseek-output-rule-20260904"
PLAN = "docs/evidence/t17-v2-deepseek-output-rule-plan-20260904.json"
APPROVAL = "docs/evidence/t17-v2-deepseek-output-rule-approval-20260904.json"
PRESERVED_CORE_COUNT = 12
PRESERVED_RESPONSE_COUNT = 42


def main() -> None:
    """仅为指定失败记录生成原响应恢复批准，不增加费用额度。"""
    previous = read_model(
        ROOT / "docs/evidence/t17-v2-deepseek-empty-rule-plan-20260904.json", ReplacementPlan
    )
    directory = ROOT / previous.output / "model2/attempt-01"
    failed = read_model(directory / "stage-result.json", StageOutcome)
    if (
        failed.status != "failed"
        or failed.gate is None
        or failed.gate.completed_core != PRESERVED_CORE_COUNT
        or failed.usage.responses != PRESERVED_RESPONSE_COUNT
        or not failed.usage.complete
    ):
        raise ValueError("output_rule_source_failure_changed")
    check = ROOT / ".tmp/t17-deepseek-20260904-01/core13-reconstruction-check-01"
    if not (check / "terminals/f22627ab916e3cb6ef9e696c.json").is_file():
        raise ValueError("original_response_reconstruction_not_verified")
    plan = previous.model_copy(
        update={
            "protocol": PROTOCOL,
            "approved_formal_prefix": (directory / "selected-sources.json")
            .relative_to(ROOT)
            .as_posix(),
            "recorded_core_raw": (directory / "raw").relative_to(ROOT).as_posix(),
            "recorded_core_ordinal": 13,
            "parallel_unspent_stage_cap_usd": Decimal("3.00"),
            "scope": (
                "原 G 24/18、360/270 不变；原响应恢复第 13 个任务，"
                "与原 H 并行且为其保留 3 美元上限。"
            ),
        }
    )
    plan = ReplacementPlan.model_validate(plan.model_dump())
    freeze_protocol(ROOT, ROOT / PROTOCOL, ROOT / previous.protocol / "preregistration.json")
    write_checked_json(ROOT / PLAN, plan)
    write_checked_json(
        ROOT / APPROVAL,
        BudgetApproval(
            approval_id="t17-v2-deepseek-output-rule-20260904",
            cost_plan_sha256=file_digest(ROOT / PLAN).sha256,
            approved_at=datetime.now(UTC),
            approved_max_total_usd=plan.allocated_usd,
            user_explicit_approval=True,
            approval_basis=(
                "用户对超限空响应修订回复允许：用量完整、实际费用未超过原预留时记为模型失败；"
                "请求上限仍为 2048，所有失败和费用保留，用原响应恢复，不重采已有结果。"
                "随后用户允许 G/H 并行：H 仅依赖已通过 F，仍保留原 3 美元上限。"
                "G 原 6 美元分配及全程 58.25 美元不变；所有已发生费用继续扣减。"
            ),
        ),
    )
    print("G_RECOVERY_READY: original 42 responses retained; core 13 uses saved responses; API=0")


if __name__ == "__main__":
    main()
