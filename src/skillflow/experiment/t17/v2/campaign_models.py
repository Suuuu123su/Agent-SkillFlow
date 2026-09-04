"""同一监督进程的费用授权、阶段结果与非秘密进度。"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field

from skillflow.experiment.t16.budget import BudgetConfig
from skillflow.experiment.t17.live_matrix import T17LiveStage
from skillflow.experiment.t17.minimal.contracts import Sha256
from skillflow.experiment.t17.v2.cost_models import StageCost
from skillflow.experiment.t17.v2.frozen import FrozenFile
from skillflow.experiment.t17.v2.run_models import PhaseGate, UnitUsage
from skillflow.models.base import NonEmptyStr, StrictModel

Money = Annotated[Decimal, Field(ge=0)]
Count = Annotated[int, Field(ge=0)]


class CredentialInputError(ValueError):
    """不可隐藏输入或输入为空时停止，不回退到文件、参数或环境变量。"""


class CampaignClaim(StrictModel):
    """一次明确批准只能启动一个监督流程，不能重复消费同一上限。"""

    approval_id: NonEmptyStr
    approval_sha256: Sha256
    cost_plan_sha256: Sha256
    approved_total_usd: Money
    output_relative_path: NonEmptyStr
    started_at: datetime


class StageBudgetProposal(StrictModel):
    """阶段请求前保存的已批分配、历史估算和当前剩余上限。"""

    stage_cost: StageCost
    attempt_number: Annotated[int, Field(ge=1)] = 1
    attempt_budget: BudgetConfig
    failed_attempt_count: Count = 0
    cost_plan_sha256: Sha256
    approval_id: NonEmptyStr
    approved_total_usd: Money
    previous_estimated_usd: Money
    previous_reserved_usd: Money
    remaining_approved_usd: Money
    projected_from: Literal["historical_planning_only", "prior_same_model_responses"]
    observed_responses: Count
    expected_estimated_usd: Money
    p95_projected_usd: Money
    retry_rule: Literal["timeout_rate_limit_stateless_connect_5xx_only"] = (
        "timeout_rate_limit_stateless_connect_5xx_only"
    )


class StageProgress(StrictModel):
    """可显示的进度只含数量和用量，没有模型正文或凭据。"""

    stage: T17LiveStage
    scheduled_core: Count
    scheduled_replay: Count
    terminal_core: Count
    terminal_replay: Count
    failed_units: Count
    model_failures: Count
    usage: UnitUsage


class StageOutcome(StrictModel):
    """执行通过与报告导出通过同时成立，才可进入下一阶段。"""

    stage: T17LiveStage
    attempt_number: Annotated[int, Field(ge=1)] = 1
    status: Literal["passed", "failed", "postprocessing_failed"]
    reason: NonEmptyStr | None = None
    gate: PhaseGate | None = None
    raw_relative_path: NonEmptyStr
    raw_manifest: FrozenFile | None = None
    interruption_manifest: FrozenFile | None = None
    dataset_relative_path: NonEmptyStr | None = None
    dataset_manifest: FrozenFile | None = None
    usage: UnitUsage


class CampaignResult(StrictModel):
    """运行结束不是项目验收完成，最终审计和远端检查另行进行。"""

    schema_version: Literal["2.0"] = "2.0"
    cost_plan_sha256: Sha256
    approval_id: NonEmptyStr
    approved_total_usd: Money
    estimated_cost_usd: Money
    reserved_cost_usd: Money
    remaining_approved_usd: Money
    stages: tuple[StageOutcome, ...]
    failed_attempts: tuple[StageOutcome, ...] = ()
    usage_complete: bool = True
    all_stages_finished: bool
    full_project_completed: Literal[False] = False
    independent_review: Literal["REVIEW_UNAVAILABLE"] = "REVIEW_UNAVAILABLE"
