"""在任何 T17 API 请求前生成可审计费用提案。"""

from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from skillflow.experiment.io import sha256_file, write_json_model
from skillflow.experiment.t16.provider import estimate_result_cost
from skillflow.experiment.t16.task_success_canary_models import T16D2CanaryRunSummary
from skillflow.experiment.t17.live_matrix import T17LiveMatrix, T17LiveStage
from skillflow.experiment.t17.live_result_store import load_live_unit_records
from skillflow.models.base import NonEmptyStr, StrictModel

NonNegativeInt = Annotated[int, Field(ge=0)]
NonNegativeMoney = Annotated[Decimal, Field(ge=0)]
PositiveMoney = Annotated[Decimal, Field(gt=0)]


class T17BudgetProposal(StrictModel):
    """历史实测外推、工程上界和待批准硬门。"""

    schema_version: Literal["0.1"] = "0.1"
    stage: T17LiveStage
    model_id: NonEmptyStr
    model_revision: NonEmptyStr
    authorization_status: Literal["pending_user_approval"] = "pending_user_approval"
    api_calls_made: Literal[0] = 0
    scheduled_core_trials: NonNegativeInt
    scheduled_replay_pairs: NonNegativeInt
    historical_summary_path: NonEmptyStr
    historical_summary_sha256: NonEmptyStr
    historical_source_kind: Literal["t16_canary", "t17_live_stage"] = "t16_canary"
    historical_observed_trials: NonNegativeInt
    historical_api_calls: NonNegativeInt
    historical_estimated_cost_usd: NonNegativeMoney
    projected_actual_usd: NonNegativeMoney
    conservative_projected_usd: NonNegativeMoney
    historical_unit_cost_p95_usd: NonNegativeMoney | None = None
    projected_p95_total_usd: NonNegativeMoney | None = None
    projection_kind: Literal[
        "engineering_upper_bound_not_statistical_p95",
        "observed_unit_p95_repriced",
    ] = "engineering_upper_bound_not_statistical_p95"
    requested_max_total_usd: PositiveMoney
    requested_max_cost_per_run_usd: PositiveMoney

    @model_validator(mode="after")
    def require_projection_evidence(self) -> Self:
        """p95 提案必须同时保存单元与总量投影。"""
        p95_fields = (
            self.historical_unit_cost_p95_usd,
            self.projected_p95_total_usd,
        )
        if self.projection_kind == "observed_unit_p95_repriced":
            if self.historical_source_kind != "t17_live_stage" or any(
                item is None for item in p95_fields
            ):
                raise PydanticCustomError(
                    "t17_budget_p95_evidence_missing",
                    "p95 提案缺少 T17 Live 单元证据",
                )
        elif any(item is not None for item in p95_fields):
            raise PydanticCustomError(
                "t17_budget_engineering_has_p95",
                "初始工程上界不得伪装为 p95",
            )
        return self


@dataclass(frozen=True, slots=True)
class BudgetProposalSourceError(ValueError):
    """历史摘要缺少完整实际费用。"""

    path: Path

    def __str__(self) -> str:
        """返回稳定的文件级诊断。"""
        return f"历史摘要缺少 observed_estimated_cost_usd: {self.path.as_posix()}"


class BudgetProposalCeilingError(ValueError):
    """p95 提案超过静态 Matrix 预算上限。"""

    __slots__ = ("proposed", "static_ceiling")

    def __init__(self, proposed: Decimal, static_ceiling: Decimal) -> None:
        """保存提案与静态上限，不自动截断。"""
        super().__init__(proposed, static_ceiling)
        self.proposed = proposed
        self.static_ceiling = static_ceiling

    def __str__(self) -> str:
        """返回稳定费用诊断。"""
        return f"proposed={self.proposed}:static_ceiling={self.static_ceiling}"


def build_initial_budget_proposal(
    historical_summary_path: Path,
    matrix: T17LiveMatrix,
) -> T17BudgetProposal:
    """按历史单 Trial 均值和 Replay 双后缀给出 2x 工程上界。"""
    historical = T16D2CanaryRunSummary.model_validate_json(
        historical_summary_path.read_text(encoding="utf-8")
    )
    historical_cost = historical.observed_estimated_cost_usd
    if historical_cost is None:
        raise BudgetProposalSourceError(historical_summary_path)
    equivalent_runs = matrix.scheduled_core_trials + (2 * matrix.scheduled_replay_pairs)
    cost_per_trial = historical_cost / Decimal(historical.observed)
    projected = cost_per_trial * Decimal(equivalent_runs)
    return T17BudgetProposal(
        stage=matrix.stage,
        model_id=matrix.provider.model_id,
        model_revision=matrix.provider.model_revision,
        scheduled_core_trials=matrix.scheduled_core_trials,
        scheduled_replay_pairs=matrix.scheduled_replay_pairs,
        historical_summary_path=historical_summary_path.as_posix(),
        historical_summary_sha256=sha256_file(historical_summary_path),
        historical_observed_trials=historical.observed,
        historical_api_calls=historical.api_call_count,
        historical_estimated_cost_usd=historical_cost,
        projected_actual_usd=projected,
        conservative_projected_usd=projected * Decimal(2),
        requested_max_total_usd=matrix.budget.max_total_usd,
        requested_max_cost_per_run_usd=matrix.budget.max_cost_per_run_usd,
    )


def write_budget_proposal(path: Path, proposal: T17BudgetProposal) -> None:
    """以不可覆盖方式写出零调用预算提案。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json_model(path, proposal)


def build_followup_budget_proposal(
    source_attempt_root: Path,
    matrix: T17LiveMatrix,
) -> T17BudgetProposal:
    """按上一阶段逐单元 Token 以目标模型价格重估 mean/p95。"""
    records = load_live_unit_records(source_attempt_root / "trial-results.jsonl")
    if not records:
        raise BudgetProposalSourceError(source_attempt_root / "trial-results.jsonl")
    repriced = tuple(
        estimate_result_cost(
            matrix.provider.pricing,
            item.telemetry.token_usage,
        )
        for item in records
    )
    unit_count = len(repriced)
    scheduled_units = matrix.scheduled_core_trials + matrix.scheduled_replay_pairs
    mean_cost = sum(repriced, start=Decimal(0)) / unit_count
    p95_cost = _decimal_percentile(repriced, Decimal("0.95"))
    projected = mean_cost * scheduled_units
    projected_p95 = p95_cost * scheduled_units
    requested_total = _ceil_cent(projected_p95 * Decimal("1.25"))
    requested_run = _ceil_cent(p95_cost * Decimal("1.50"))
    if (
        requested_total > matrix.budget.max_total_usd
        or requested_run > matrix.budget.max_cost_per_run_usd
    ):
        raise BudgetProposalCeilingError(
            max(requested_total, requested_run),
            max(
                matrix.budget.max_total_usd,
                matrix.budget.max_cost_per_run_usd,
            ),
        )
    summary_path = source_attempt_root / "live-summary.json"
    return T17BudgetProposal(
        stage=matrix.stage,
        model_id=matrix.provider.model_id,
        model_revision=matrix.provider.model_revision,
        scheduled_core_trials=matrix.scheduled_core_trials,
        scheduled_replay_pairs=matrix.scheduled_replay_pairs,
        historical_summary_path=summary_path.as_posix(),
        historical_summary_sha256=sha256_file(summary_path),
        historical_source_kind="t17_live_stage",
        historical_observed_trials=unit_count,
        historical_api_calls=sum(item.telemetry.api_call_count for item in records),
        historical_estimated_cost_usd=sum(
            (item.telemetry.estimated_cost_usd for item in records),
            start=Decimal(0),
        ),
        projected_actual_usd=projected,
        conservative_projected_usd=projected_p95,
        historical_unit_cost_p95_usd=p95_cost,
        projected_p95_total_usd=projected_p95,
        projection_kind="observed_unit_p95_repriced",
        requested_max_total_usd=requested_total,
        requested_max_cost_per_run_usd=requested_run,
    )


def _decimal_percentile(
    values: tuple[Decimal, ...],
    probability: Decimal,
) -> Decimal:
    ordered = sorted(values)
    position = Decimal(len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (Decimal(1) - weight) + ordered[upper] * weight


def _ceil_cent(value: Decimal) -> Decimal:
    return max(
        Decimal("0.01"),
        value.quantize(Decimal("0.01"), rounding=ROUND_CEILING),
    )
