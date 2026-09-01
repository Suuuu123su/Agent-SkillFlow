"""T16-C 0.2 离线重分析报告模型。"""

from typing import Annotated, Literal, NoReturn, Self

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from skillflow.experiment.t16.live_metric_models import UnavailableFormalMetric
from skillflow.experiment.t16.preregistration_models import PairRole
from skillflow.models.advanced_metrics import DerivedMetric
from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.matrix_design import HiaaCell
from skillflow.models.metrics import RatioMetric
from skillflow.models.references import EffectSelectorRef

NonNegativeInt = Annotated[int, Field(ge=0)]
Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
AuthorizationBasis = Literal["preregistered_structured_authorization_flag"]


class ObservationAccounting(StrictModel):
    """区分预定、实际到达、有效、缺失和拒绝的 Trial 集合。"""

    scheduled_count: NonNegativeInt
    observed_count: NonNegativeInt
    valid_count: NonNegativeInt
    missing_count: NonNegativeInt
    refusal_count: NonNegativeInt
    no_call_count: NonNegativeInt
    schema_rejection_count: NonNegativeInt
    infrastructure_failure_count: NonNegativeInt
    other_invalid_count: NonNegativeInt
    scheduled_trial_ids: tuple[NonEmptyStr, ...]
    observed_trial_ids: tuple[NonEmptyStr, ...]
    valid_trial_ids: tuple[NonEmptyStr, ...]
    missing_trial_ids: tuple[NonEmptyStr, ...]
    refusal_trial_ids: tuple[NonEmptyStr, ...]
    no_call_trial_ids: tuple[NonEmptyStr, ...]
    schema_rejection_trial_ids: tuple[NonEmptyStr, ...]
    infrastructure_failure_trial_ids: tuple[NonEmptyStr, ...]
    other_invalid_trial_ids: tuple[NonEmptyStr, ...]

    @model_validator(mode="after")
    def require_set_accounting(self) -> Self:
        """计数必须可由公开 ID 集合复算，缺失不能伪装为 false。"""
        counted = (
            (self.scheduled_count, self.scheduled_trial_ids),
            (self.observed_count, self.observed_trial_ids),
            (self.valid_count, self.valid_trial_ids),
            (self.missing_count, self.missing_trial_ids),
            (self.refusal_count, self.refusal_trial_ids),
            (self.no_call_count, self.no_call_trial_ids),
            (self.schema_rejection_count, self.schema_rejection_trial_ids),
            (
                self.infrastructure_failure_count,
                self.infrastructure_failure_trial_ids,
            ),
            (self.other_invalid_count, self.other_invalid_trial_ids),
        )
        if any(count != len(identifiers) for count, identifiers in counted):
            self._invalid("观察计数必须等于对应 trial_id 数量")
        if any(len(set(identifiers)) != len(identifiers) for _, identifiers in counted):
            self._invalid("观察集合内 trial_id 不能重复")
        scheduled = set(self.scheduled_trial_ids)
        observed = set(self.observed_trial_ids)
        missing = set(self.missing_trial_ids)
        if observed & missing or scheduled != observed | missing:
            self._invalid("scheduled 必须由 observed 与 missing 无交并集组成")
        if not set(self.valid_trial_ids).issubset(observed):
            self._invalid("valid 必须是 observed 子集")
        failure_sets = (
            set(self.refusal_trial_ids),
            set(self.no_call_trial_ids),
            set(self.schema_rejection_trial_ids),
            set(self.infrastructure_failure_trial_ids),
            set(self.other_invalid_trial_ids),
        )
        if any(not identifiers.issubset(observed) for identifiers in failure_sets):
            self._invalid("失败分类必须是 observed 子集")
        invalid = observed - set(self.valid_trial_ids)
        if not invalid.issubset(set().union(*failure_sets)):
            self._invalid("失败分类必须覆盖 observed-valid 的全部记录")
        return self

    @staticmethod
    def _invalid(detail: str) -> NoReturn:
        raise PydanticCustomError("t16c_reanalysis_accounting", detail)


class ExecutionRateAccounting(StrictModel):
    """同一执行事实在 scheduled、observed 与 valid 三种分母下的比率。"""

    observations: ObservationAccounting
    executed_count: NonNegativeInt
    executed_trial_ids: tuple[NonEmptyStr, ...]
    receipt_ids: tuple[NonEmptyStr, ...]
    evidence_status: Literal["complete", "partial", "not_available"] = "complete"
    evidence_unavailable_trial_ids: tuple[NonEmptyStr, ...] = ()
    scheduled_rate: RatioMetric
    observed_rate: RatioMetric
    valid_rate: RatioMetric

    @model_validator(mode="after")
    def require_execution_accounting(self) -> Self:
        """每个执行 Trial 必须有效、有 Receipt 且进入三种比率的同一分子。"""
        self._require_execution_partition()
        self._require_evidence_partition()
        self._require_rate_denominators()
        return self

    def _require_execution_partition(self) -> None:
        """验证执行 Trial、Receipt 与 valid 集合的一一对应。"""
        if self.executed_count != len(self.executed_trial_ids):
            self._invalid("执行计数必须等于 executed trial_id 数量")
        if len(set(self.executed_trial_ids)) != len(self.executed_trial_ids):
            self._invalid("executed trial_id 不能重复")
        if self.executed_count != len(self.receipt_ids):
            self._invalid("每个执行 Trial 必须精确绑定一个 Receipt")
        if not set(self.executed_trial_ids).issubset(self.observations.valid_trial_ids):
            self._invalid("执行 Trial 必须进入 valid 集合")

    def _require_evidence_partition(self) -> None:
        """验证不可识别 Trial 分区与 evidence status 一致。"""
        unavailable = self.evidence_unavailable_trial_ids
        if len(set(unavailable)) != len(unavailable):
            self._invalid("证据不可用 trial_id 不能重复")
        if not set(unavailable).issubset(self.observations.scheduled_trial_ids):
            self._invalid("证据不可用 trial_id 必须属于 scheduled 集合")
        if set(unavailable) & set(self.executed_trial_ids):
            self._invalid("证据不可用 Trial 不能同时进入执行分子")
        expected_status = (
            "complete"
            if not unavailable
            else (
                "not_available"
                if len(unavailable) == self.observations.scheduled_count
                else "partial"
            )
        )
        if self.evidence_status != expected_status:
            self._invalid("证据状态与不可用 Trial 集不一致")

    def _require_rate_denominators(self) -> None:
        """按证据完整性验证 scheduled、observed 与 valid 三种分母。"""
        if self.evidence_status == "complete":
            rates = (
                (self.scheduled_rate, self.observations.scheduled_count),
                (self.observed_rate, self.observations.observed_count),
                (self.valid_rate, self.observations.valid_count),
            )
            if any(
                rate.numerator != self.executed_count or rate.denominator != denominator
                for rate, denominator in rates
            ):
                self._invalid("执行率必须共享执行分子并使用对应观察分母")
        else:
            unavailable_rates = (self.scheduled_rate, self.observed_rate)
            if any(
                rate.numerator != 0 or rate.denominator != 0 or rate.value is not None
                for rate in unavailable_rates
            ):
                self._invalid("证据不完整时 scheduled/observed 执行率必须为 N/A")
            if (
                self.valid_rate.numerator != self.executed_count
                or self.valid_rate.denominator != self.observations.valid_count
            ):
                self._invalid("valid-only 执行率必须使用可识别证据子集")

    @staticmethod
    def _invalid(detail: str) -> NoReturn:
        raise PydanticCustomError("t16c_reanalysis_execution", detail)


class ReanalysisHiaaCellMetric(StrictModel):
    """HIAA 单元格的多分母敏感性结果。"""

    cell: HiaaCell
    execution: ExecutionRateAccounting


class ReanalysisHiaaSummary(StrictModel):
    """保留 scheduled 主口径并公开 valid-only 敏感性。"""

    harm_selector: EffectSelectorRef
    p00: ReanalysisHiaaCellMetric
    p01: ReanalysisHiaaCellMetric
    p10: ReanalysisHiaaCellMetric
    p11: ReanalysisHiaaCellMetric
    hiaa_run_scheduled: DerivedMetric
    hiaa_run_valid: DerivedMetric

    @model_validator(mode="after")
    def require_cell_order(self) -> Self:
        """四个字段必须携带对应 cell。"""
        if tuple(item.cell for item in (self.p00, self.p01, self.p10, self.p11)) != tuple(HiaaCell):
            raise PydanticCustomError("t16c_reanalysis_hiaa_order", "HIAA 四格顺序错误")
        return self


class ReanalysisConditionRate(StrictModel):
    """授权条件的目标 Effect 操作率与观察核算。"""

    condition_id: NonEmptyStr
    execution: ExecutionRateAccounting


class ReanalysisM2SessionRate(StrictModel):
    """M2 指定 role/session 的实际到达和目标 Receipt 比率。"""

    pair_role: PairRole
    session_index: Literal[1, 3]
    execution: ExecutionRateAccounting


class TargetExecutionAuthorizationSummary(StrictModel):
    """按预注册结构化授权标记拆分目标执行，不冒充 Grant Hook。"""

    authorization_basis: AuthorizationBasis
    formal_grant_observation_status: Literal["not_available"] = "not_available"
    target_execution_count: NonNegativeInt
    structured_authorized_execution_count: NonNegativeInt
    structured_unauthorized_execution_count: NonNegativeInt
    target_trial_ids: tuple[NonEmptyStr, ...]
    structured_authorized_trial_ids: tuple[NonEmptyStr, ...]
    structured_unauthorized_trial_ids: tuple[NonEmptyStr, ...]
    receipt_ids: tuple[NonEmptyStr, ...]
    evidence_status: Literal["complete", "partial", "not_available"] = "complete"
    count_semantics: Literal["exact", "identifiable_lower_bound"] = "exact"
    unclassified_receipted_trial_count: NonNegativeInt = 0
    unclassified_receipted_trial_ids: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def require_partition(self) -> Self:
        """结构化授权两类必须无交且精确覆盖全部目标执行。"""
        target = set(self.target_trial_ids)
        authorized = set(self.structured_authorized_trial_ids)
        unauthorized = set(self.structured_unauthorized_trial_ids)
        counts = (
            (self.target_execution_count, self.target_trial_ids),
            (self.structured_authorized_execution_count, self.structured_authorized_trial_ids),
            (self.structured_unauthorized_execution_count, self.structured_unauthorized_trial_ids),
        )
        if any(count != len(identifiers) for count, identifiers in counts):
            raise PydanticCustomError("t16c_reanalysis_auth_count", "授权执行计数不一致")
        if authorized & unauthorized or target != authorized | unauthorized:
            raise PydanticCustomError("t16c_reanalysis_auth_partition", "授权执行分区不完整")
        if len(self.receipt_ids) != self.target_execution_count:
            raise PydanticCustomError(
                "t16c_reanalysis_auth_receipt", "目标执行必须逐条绑定 Receipt"
            )
        unclassified = self.unclassified_receipted_trial_ids
        if self.unclassified_receipted_trial_count != len(unclassified):
            raise PydanticCustomError(
                "t16c_reanalysis_auth_unclassified_count",
                "未分类 Receipt 计数不一致",
            )
        if len(set(unclassified)) != len(unclassified) or target & set(unclassified):
            raise PydanticCustomError(
                "t16c_reanalysis_auth_unclassified_partition",
                "未分类 Receipt Trial 必须唯一且不进入已识别目标分区",
            )
        expected_status = (
            "complete" if not unclassified else ("partial" if target else "not_available")
        )
        expected_semantics = "exact" if not unclassified else "identifiable_lower_bound"
        if self.evidence_status != expected_status or self.count_semantics != expected_semantics:
            raise PydanticCustomError(
                "t16c_reanalysis_auth_evidence_status",
                "目标执行证据状态与未分类 Receipt 不一致",
            )
        return self


class DesignLabeledOperationalUea(StrictModel):
    """只按设计标签计算的操作性 UEA，不等于正式 Grant 判定。"""

    authorization_basis: AuthorizationBasis
    unauthorized_executed_count: NonNegativeInt
    affected_trial_count: NonNegativeInt
    affected_trial_ids: tuple[NonEmptyStr, ...]
    receipt_ids: tuple[NonEmptyStr, ...]
    evidence_status: Literal["complete", "partial", "not_available"] = "complete"
    count_semantics: Literal["exact", "identifiable_lower_bound"] = "exact"
    unclassified_receipted_trial_ids: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def require_receipts(self) -> Self:
        """每条设计标记未授权执行必须有 Trial 与 Receipt。"""
        expected = len(self.affected_trial_ids)
        if (
            self.unauthorized_executed_count != expected
            or self.affected_trial_count != expected
            or len(self.receipt_ids) != expected
        ):
            raise PydanticCustomError("t16c_reanalysis_operational_uea", "操作性 UEA 计数不一致")
        unclassified = self.unclassified_receipted_trial_ids
        expected_status = (
            "complete"
            if not unclassified
            else ("partial" if self.affected_trial_ids else "not_available")
        )
        expected_semantics = "exact" if not unclassified else "identifiable_lower_bound"
        if (
            len(set(unclassified)) != len(unclassified)
            or set(unclassified) & set(self.affected_trial_ids)
            or self.evidence_status != expected_status
            or self.count_semantics != expected_semantics
        ):
            raise PydanticCustomError(
                "t16c_reanalysis_operational_uea_evidence",
                "操作性 UEA 证据状态与未分类 Receipt 不一致",
            )
        return self


class LegacyOutcomeSummary(StrictModel):
    """保留 0.1 三分类，防止重分析改写原始证据。"""

    harm_count: NonNegativeInt
    completed_without_harm_count: NonNegativeInt
    invalid_count: NonNegativeInt
    refusal_count: NonNegativeInt


class LiveReanalysisReport(StrictModel):
    """不覆盖 0.1 证据的 T16-C 0.2 离线重分析报告。"""

    schema_version: Literal["0.2"] = "0.2"
    simulation_only: Literal[False] = False
    live_model: Literal[True] = True
    external_effects_simulated: Literal[True] = True
    adapter_mode: Literal["direct_prompt_contract_validated"] = "direct_prompt_contract_validated"
    research_conclusion_eligible: Literal[False] = False
    correction_of: Literal["t16c-live-metrics-v0.1"] = "t16c-live-metrics-v0.1"
    legacy_harm_semantics: Literal["selector_effect_with_receipt_not_attack_success"] = (
        "selector_effect_with_receipt_not_attack_success"
    )
    source_trial_results_path: NonEmptyStr
    source_trial_results_sha256: Sha256Hex
    source_record_count: NonNegativeInt
    raw_evidence_immutable: Literal[True] = True
    repeat_is_independent_statistical_unit: Literal[False] = False
    legacy_outcomes: LegacyOutcomeSummary
    hiaa: ReanalysisHiaaSummary
    authorization_operational_rates: tuple[ReanalysisConditionRate, ...]
    m2_operational_rates: tuple[ReanalysisM2SessionRate, ...]
    target_execution_authorization: TargetExecutionAuthorizationSummary
    operational_design_labeled_uea: DesignLabeledOperationalUea
    formal_uea: UnavailableFormalMetric
    alr: UnavailableFormalMetric
    rir_1: UnavailableFormalMetric
    rir_3: UnavailableFormalMetric
    provenance: UnavailableFormalMetric
    provenance_not_available_count: NonNegativeInt

    @model_validator(mode="after")
    def require_source_counts(self) -> Self:
        """来源总数必须与 legacy 三分类和 provenance N/A 覆盖一致。"""
        total = (
            self.legacy_outcomes.harm_count
            + self.legacy_outcomes.completed_without_harm_count
            + self.legacy_outcomes.invalid_count
        )
        if total != self.source_record_count:
            raise PydanticCustomError("t16c_reanalysis_source_count", "legacy 三分类未覆盖来源记录")
        if self.provenance_not_available_count != self.source_record_count:
            raise PydanticCustomError(
                "t16c_reanalysis_provenance_count", "provenance N/A 未覆盖来源"
            )
        return self
