"""T16-B Matrix、故障、费用与总摘要模型。"""

from decimal import Decimal
from enum import StrEnum, unique
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from skillflow.experiment.t16.budget import BudgetLimit
from skillflow.experiment.t16.dry_run_records import CostChainProfile
from skillflow.experiment.t16.provider import PricingRates, TokenUsage
from skillflow.models.base import NonEmptyStr, StrictModel

NonNegativeInt = Annotated[int, Field(ge=0)]
PositiveInt = Annotated[int, Field(ge=1)]
NonNegativeMoney = Annotated[Decimal, Field(ge=0)]


@unique
class OperationalDisposition(StrEnum):
    """不改变三分类定义的操作性细分。"""

    HARM = "harm"
    COMPLETED_WITHOUT_HARM = "completed_without_harm"
    REFUSAL = "refusal"
    NO_CALL = "no_call"
    INVALID_OTHER = "invalid_other"


@unique
class DuplicateHandling(StrEnum):
    """重复链进入统计前的处理策略。"""

    REJECT = "reject_duplicate_trial_id"


@unique
class FailureInjectionKind(StrEnum):
    """T16-B 必须覆盖的失败及分类对照。"""

    PROVIDER_TIMEOUT = "provider_timeout"
    RATE_LIMIT = "rate_limit"
    GATEWAY_CRASH = "gateway_crash"
    MISSING_RECEIPT = "missing_receipt"
    USAGE_METADATA_MISSING = "usage_metadata_missing"
    RUN_COST = "run_cost"
    TOTAL_COST = "total_cost"
    AGENT_STEPS = "agent_steps"
    RETRY_LIMIT = "retry_limit"
    UNEXPECTED_NETWORK = "unexpected_network"
    REFUSAL = "refusal"
    NO_CALL = "no_call"


@unique
class CostMode(StrEnum):
    """模拟费用的两个边界。"""

    NORMAL = "normal"
    WORST_CASE = "worst_case"


@unique
class AttackSuccessRateStatus(StrEnum):
    """Fake 演练对现实攻击率的适用性。"""

    NOT_APPLICABLE = "not_applicable"


@unique
class ExternalReviewStatus(StrEnum):
    """独立外部复审的实际状态。"""

    REVIEW_UNAVAILABLE = "review_unavailable"


class OperationalCounts(StrictModel):
    """仅用于管线检查、不能视为现实 ASR 的计数。"""

    harm: NonNegativeInt
    completed_without_harm: NonNegativeInt
    refusal: NonNegativeInt
    no_call: NonNegativeInt
    invalid_other: NonNegativeInt

    @property
    def total(self) -> int:
        """返回互斥操作分类总数。"""
        return (
            self.harm
            + self.completed_without_harm
            + self.refusal
            + self.no_call
            + self.invalid_other
        )


class StatisticalDenominators(StrictModel):
    """忽略 Fake Slot 与 repeat 的唯一预注册单位。"""

    unique_condition_instances: PositiveInt
    unique_pair_instances: PositiveInt
    fake_repeats_are_independent_samples: Literal[False] = False


class MatrixIntegrityReport(StrictModel):
    """720 链的机械完整性报告。"""

    schema_version: Literal["0.1"] = "0.1"
    simulation_only: Literal[True] = True
    expected_trial_count: PositiveInt
    scheduled_trial_count: PositiveInt
    unique_trial_id_count: PositiveInt
    slot_count: PositiveInt
    condition_count: PositiveInt
    semantic_instances_per_condition: PositiveInt
    repeats_per_instance: PositiveInt
    target_neutral_pair_ids_aligned: bool
    hiaa_shared_harm_selector: bool
    m2_sessions_exact: bool
    a1_neutralization_exact: bool
    duplicate_handling: DuplicateHandling
    denominators: StatisticalDenominators
    operational_counts: OperationalCounts

    @model_validator(mode="after")
    def require_complete_matrix(self) -> Self:
        """不允许把部分矩阵写成完整报告。"""
        counts = (
            self.expected_trial_count,
            self.scheduled_trial_count,
            self.unique_trial_id_count,
            self.operational_counts.total,
        )
        checks = (
            self.target_neutral_pair_ids_aligned,
            self.hiaa_shared_harm_selector,
            self.m2_sessions_exact,
            self.a1_neutralization_exact,
        )
        if len(set(counts)) != 1 or not all(checks):
            raise PydanticCustomError("t16b_matrix_incomplete", "T16-B Matrix 完整性检查未闭合")
        return self


class FailureInjectionResult(StrictModel):
    """一次本地失败注入的可审计结果。"""

    kind: FailureInjectionKind
    blocked: bool
    observed_signal: NonEmptyStr
    disposition: OperationalDisposition


class FailureInjectionReport(StrictModel):
    """全部故障与分类对照的汇总。"""

    schema_version: Literal["0.1"] = "0.1"
    simulation_only: Literal[True] = True
    results: tuple[FailureInjectionResult, ...]
    all_blocked: bool
    classifications_are_distinct: bool

    @model_validator(mode="after")
    def require_all_injections(self) -> Self:
        """报告必须精确覆盖封闭故障集合且全部安全收敛。"""
        kinds = tuple(item.kind for item in self.results)
        dispositions = {item.disposition for item in self.results}
        required_dispositions = {
            OperationalDisposition.REFUSAL,
            OperationalDisposition.NO_CALL,
            OperationalDisposition.INVALID_OTHER,
        }
        if set(kinds) != set(FailureInjectionKind) or len(set(kinds)) != len(kinds):
            raise PydanticCustomError("t16b_failure_coverage", "失败注入集合不完整")
        if not self.all_blocked or not all(item.blocked for item in self.results):
            raise PydanticCustomError("t16b_failure_unblocked", "存在未被安全收敛的失败")
        if not self.classifications_are_distinct or not required_dispositions.issubset(
            dispositions
        ):
            raise PydanticCustomError("t16b_failure_classification", "失败分类未保持互斥语义")
        return self


class CostCaseResult(StrictModel):
    """一个链长和费用边界的机械估算。"""

    profile: CostChainProfile
    mode: CostMode
    token_usage: TokenUsage
    api_call_count: PositiveInt
    estimated_cost_usd: NonNegativeMoney


class BudgetStopEvidence(StrictModel):
    """达到预算后停止且保留既有 JSONL 的证据。"""

    limit: BudgetLimit
    attempted_result_count: PositiveInt
    saved_result_count: PositiveInt
    existing_results_saved: bool
    saved_results_sha256: NonEmptyStr


class CostSimulationReport(StrictModel):
    """不代表真实账单的模拟 Token 与费用保护报告。"""

    schema_version: Literal["0.1"] = "0.1"
    simulation_only: Literal[True] = True
    rates_are_hypothetical: Literal[True] = True
    pricing: PricingRates
    cases: tuple[CostCaseResult, ...]
    fake_provider_billed_cost_usd: NonNegativeMoney = Decimal(0)
    single_run_limit_blocked: bool
    total_limit_blocked: bool
    agent_step_limit_blocked: bool
    retry_limit_blocked: bool
    partial_save: BudgetStopEvidence

    @model_validator(mode="after")
    def require_complete_cost_rehearsal(self) -> Self:
        """三种链长必须各有正常/最坏费用，四类边界必须被阻断。"""
        keys = {(item.profile, item.mode) for item in self.cases}
        expected = {(profile, mode) for profile in CostChainProfile for mode in CostMode}
        guards = (
            self.single_run_limit_blocked,
            self.total_limit_blocked,
            self.agent_step_limit_blocked,
            self.retry_limit_blocked,
            self.partial_save.existing_results_saved,
        )
        if self.fake_provider_billed_cost_usd != 0:
            raise PydanticCustomError("t16b_fake_cost_nonzero", "Fake Provider 账单费用必须为 0")
        if keys != expected or len(keys) != len(self.cases) or not all(guards):
            raise PydanticCustomError("t16b_cost_incomplete", "费用演练未覆盖全部边界")
        return self


class T16BDryRunSummary(StrictModel):
    """可提交的 T16-B 总报告；明确排除现实安全结论。"""

    schema_version: Literal["0.1"] = "0.1"
    id: NonEmptyStr
    simulation_only: Literal[True] = True
    real_attack_success_rate_status: Literal[AttackSuccessRateStatus.NOT_APPLICABLE]
    real_model_safety_conclusion_supported: Literal[False] = False
    fake_repeats_are_independent_samples: Literal[False] = False
    external_review_status: Literal[ExternalReviewStatus.REVIEW_UNAVAILABLE]
    model_slots: tuple[NonEmptyStr, NonEmptyStr]
    trial_results_artifact: NonEmptyStr
    trial_results_sha256: NonEmptyStr
    matrix_integrity: MatrixIntegrityReport
    failure_injection: FailureInjectionReport
    cost_simulation: CostSimulationReport
