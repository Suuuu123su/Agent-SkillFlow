"""只汇总已关闭尝试的真实用量；旧模型与失败费用不因撤回而消失。"""

# ruff: noqa: INP001

import argparse
from decimal import Decimal
from pathlib import Path
from typing import Literal

from skillflow.experiment.t17.minimal.artifacts import write_checked_json
from skillflow.experiment.t17.v2.campaign_models import CampaignResult, StageOutcome
from skillflow.experiment.t17.v2.cost_models import BudgetApproval
from skillflow.experiment.t17.v2.dataset_writing import guard_public
from skillflow.experiment.t17.v2.frozen import inside
from skillflow.experiment.t17.v2.loading import read_model
from skillflow.experiment.t17.v2.run_models import UnitUsage
from skillflow.models.base import StrictModel

FIRST = "runs/t17-v2-live-20260904-01/campaign-result.json"
LEGACY = "runs/t17-v2-live-20260904-02/campaign-after-attempt-007.json"
NEW_CAMPAIGNS = {
    "deepseek": "runs/t17-v2-deepseek-20260904-01",
    "luna_defense": "runs/t17-v2-luna-defense-20260904-01",
}


class ExpenseRow(StrictModel):
    """费用行对应一次真实尝试，不是选入正式分析的任务子集。"""

    source_document: str
    source_item: str
    cohort: str
    stage: str
    attempt: int
    outcome_status: str
    usage: UnitUsage


class ExpenseReport(StrictModel):
    """完整保守预算可核算，未知响应不能假装成已知账单。"""

    schema_version: Literal["2.0"] = "2.0"
    scope: Literal["all_closed_v2_attempts_including_withdrawn_and_failed"] = (
        "all_closed_v2_attempts_including_withdrawn_and_failed"
    )
    rows: tuple[ExpenseRow, ...]
    observed_usage: UnitUsage
    approved_total_usd: Decimal
    remaining_reserved_budget_usd: Decimal
    pending_attempt_directories: tuple[str, ...]
    measurement_status: Literal["measured", "incomplete"]
    invoice_verified: Literal[False] = False
    notes: tuple[str, ...] = (
        "按冻结费率估算，保守占用包含响应状态未知的请求，不是供应商账单。",
        "续跑结果费用仅累计该次新增网络请求；保留前缀或本地恢复响应不重复算作 API 调用。",
        "科学指标按各阶段选定记录计算；费用按所有实际尝试计算，两种分母不可混用。",
        "历史未知响应用量保持 incomplete；最终保留样本用量完整不意味着失败尝试用量已知。",
    )


def expense_row(source: str, item: str, cohort: str, outcome: StageOutcome) -> ExpenseRow:
    """响应编号留在原逐请求账本，费用汇总保留来源和全部计数。"""
    return ExpenseRow(
        source_document=source,
        source_item=item,
        cohort=cohort,
        stage=outcome.stage.value,
        attempt=outcome.attempt_number,
        outcome_status=outcome.status,
        usage=outcome.usage.model_copy(update={"response_ids": ()}),
    )


def summed_usage(rows: tuple[ExpenseRow, ...]) -> UnitUsage:
    """不按模型、通过状态或选中样本过滤已发生费用。"""
    if len({(r.source_document, r.source_item) for r in rows}) != len(rows):
        raise ValueError("expense_duplicate_source")
    uses = tuple(r.usage for r in rows)
    return UnitUsage(
        complete=all(u.complete for u in uses),
        missing_reason=next((u.missing_reason for u in uses if not u.complete), None),
        api_calls=sum(u.api_calls for u in uses),
        responses=sum(u.responses for u in uses),
        input_tokens=sum(u.input_tokens for u in uses),
        cached_input_tokens=sum(u.cached_input_tokens for u in uses),
        cache_write_tokens=sum(u.cache_write_tokens for u in uses),
        output_tokens=sum(u.output_tokens for u in uses),
        reasoning_tokens=sum(u.reasoning_tokens for u in uses),
        latency_ms=sum(u.latency_ms for u in uses),
        estimated_cost_usd=sum((u.estimated_cost_usd for u in uses), Decimal(0)),
        reserved_cost_usd=sum((u.reserved_cost_usd for u in uses), Decimal(0)),
    )


def collect_expenses(root: Path) -> ExpenseReport:
    """费用快照与逐尝试相加必须一致；仍运行的尝试明确列出。"""
    rows: list[ExpenseRow] = []
    for source, label in (
        (FIRST, "initial_credential_attempt"),
        (LEGACY, "legacy_before_deepseek"),
    ):
        result = read_model(inside(root, source), CampaignResult)
        before = len(rows)
        for field in ("stages", "failed_attempts"):
            for index, outcome in enumerate(getattr(result, field)):
                rows.append(expense_row(source, f"{field}[{index}]", label, outcome))
        subtotal = summed_usage(tuple(rows[before:]))
        if (subtotal.estimated_cost_usd, subtotal.reserved_cost_usd) != (
            result.estimated_cost_usd,
            result.reserved_cost_usd,
        ):
            raise ValueError("expense_historical_snapshot_mismatch")
    pending = []
    for cohort, folder in NEW_CAMPAIGNS.items():
        for directory in sorted(inside(root, folder).glob("*/attempt-*")):
            outcome_path = directory / "stage-result.json"
            if not outcome_path.is_file():
                pending.append(directory.relative_to(root).as_posix())
                continue
            rows.append(
                expense_row(
                    outcome_path.relative_to(root).as_posix(),
                    "outcome",
                    cohort,
                    read_model(outcome_path, StageOutcome),
                )
            )
    total = summed_usage(tuple(rows))
    approval = read_model(inside(root, "docs/evidence/t17-v2-budget-approval.json"), BudgetApproval)
    if total.reserved_cost_usd > approval.approved_max_total_usd:
        raise ValueError("expense_original_budget_exceeded")
    return ExpenseReport(
        rows=tuple(rows),
        observed_usage=total,
        approved_total_usd=approval.approved_max_total_usd,
        remaining_reserved_budget_usd=approval.approved_max_total_usd - total.reserved_cost_usd,
        pending_attempt_directories=tuple(pending),
        measurement_status="measured" if total.complete and not pending else "incomplete",
    )


def main() -> None:
    """输出新文件，不覆盖历史费用记录；不包含请求头、正文或密钥。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    result = collect_expenses(root)
    guard_public(result.model_dump_json())
    write_checked_json(inside(root, args.output), result)
    print(  # noqa: T201
        f"closed_attempts={len(result.rows)}; "
        f"pending={len(result.pending_attempt_directories)}; "
        f"known_estimated_usd={result.observed_usage.estimated_cost_usd}; "
        f"reserved_usd={result.observed_usage.reserved_cost_usd}; "
        f"status={result.measurement_status}",
    )


if __name__ == "__main__":
    main()
