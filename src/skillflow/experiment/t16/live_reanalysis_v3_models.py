"""T16-C 0.3 设计绑定与原始审计重分析报告模型。"""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from skillflow.experiment.t16.live_metric_models import UnavailableFormalMetric
from skillflow.experiment.t16.live_reanalysis_models import (
    DesignLabeledOperationalUea,
    LegacyOutcomeSummary,
    ReanalysisConditionRate,
    ReanalysisHiaaSummary,
    ReanalysisM2SessionRate,
    TargetExecutionAuthorizationSummary,
)
from skillflow.models.base import NonEmptyStr, StrictModel

NonNegativeInt = Annotated[int, Field(ge=0)]
Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
M2ExecutionBasis = Literal[
    "per_session_expected_alias_tool_audit",
    "mixed_per_session_audit_and_legacy_observation",
    "legacy_session_observation_fallback",
]


class LiveDesignBinding(StrictModel):
    """冻结设计、完整 Trial 集和实际模型输入清单的公开绑定。"""

    preregistration_path: NonEmptyStr
    preregistration_sha256: Sha256Hex
    preregistration_id: NonEmptyStr
    preregistration_schema_version: Literal["0.1", "0.2"]
    matrix_path: NonEmptyStr
    matrix_sha256: Sha256Hex
    matrix_id: NonEmptyStr
    matrix_schema_version: Literal["0.1", "0.2"]
    matrix_kind: Literal["model1"] = "model1"
    complete_trial_set: Literal[True] = True
    expected_trial_count: NonNegativeInt
    expected_trial_ids: tuple[NonEmptyStr, ...]
    observed_trial_ids: tuple[NonEmptyStr, ...]
    model_input_manifest_sha256: Sha256Hex
    unique_model_input_count: NonNegativeInt

    @model_validator(mode="after")
    def require_complete_sorted_sets(self) -> Self:
        """完整集合必须相等、唯一且按 trial_id 确定排序。"""
        expected = self.expected_trial_ids
        observed = self.observed_trial_ids
        if expected != tuple(sorted(expected)) or observed != tuple(sorted(observed)):
            self._invalid("设计绑定的 trial_id 必须确定排序")
        if len(set(expected)) != len(expected) or len(set(observed)) != len(observed):
            self._invalid("设计绑定的 trial_id 不能重复")
        if self.expected_trial_count != len(expected):
            self._invalid("expected_trial_count 与 Matrix Trial 集不一致")
        if self.preregistration_schema_version != self.matrix_schema_version:
            self._invalid("预注册与 Matrix Schema 版本必须一致")
        if expected != observed:
            self._invalid("观察 Trial 必须与冻结 Matrix 完整集合精确相等")
        if self.unique_model_input_count > len(observed):
            self._invalid("唯一模型输入数不能超过 Trial 数")
        return self

    @staticmethod
    def _invalid(detail: str) -> None:
        raise PydanticCustomError("t16c_v3_design_binding", detail)


class AuditEvidenceBasis(StrictModel):
    """公开各操作性分子的证据来源及旧记录兼容限制。"""

    hiaa_execution_basis: Literal[
        "accepted_session_tool_audit_matching_harm_selector_with_receipt"
    ] = "accepted_session_tool_audit_matching_harm_selector_with_receipt"
    authorization_execution_basis: Literal[
        "accepted_session_tool_audit_matching_expected_alias_with_receipt"
    ] = "accepted_session_tool_audit_matching_expected_alias_with_receipt"
    observation_classification_basis: Literal[
        "legacy_trial_and_session_terminal_flags_for_valid_refusal_and_failures"
    ] = "legacy_trial_and_session_terminal_flags_for_valid_refusal_and_failures"
    m2_execution_basis: M2ExecutionBasis
    legacy_m2_fallback_trial_ids: tuple[NonEmptyStr, ...] = ()
    authorization_alias_unavailable_trial_ids: tuple[NonEmptyStr, ...] = ()
    target_alias_unavailable_trial_ids: tuple[NonEmptyStr, ...] = ()
    compatibility_limitations: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def require_explicit_compatibility_limitations(self) -> Self:
        """任何旧证据回退或 alias 缺失都必须公开限制。"""
        identifier_groups = (
            self.legacy_m2_fallback_trial_ids,
            self.authorization_alias_unavailable_trial_ids,
            self.target_alias_unavailable_trial_ids,
        )
        if any(len(set(items)) != len(items) for items in identifier_groups):
            self._invalid("兼容性 trial_id 不能重复")
        has_fallback = bool(self.legacy_m2_fallback_trial_ids)
        if has_fallback == (self.m2_execution_basis == "per_session_expected_alias_tool_audit"):
            self._invalid("M2 evidence basis 与 legacy fallback 集不一致")
        has_limitation = any(identifier_groups)
        if has_limitation != bool(self.compatibility_limitations):
            self._invalid("兼容性限制必须与回退或缺失证据同步公开")
        return self

    @staticmethod
    def _invalid(detail: str) -> None:
        raise PydanticCustomError("t16c_v3_evidence_basis", detail)


class LiveReanalysisReportV3(StrictModel):
    """保留旧证据且绑定冻结设计的 T16-C 0.3 报告。"""

    schema_version: Literal["0.3"] = "0.3"
    simulation_only: Literal[False] = False
    live_model: Literal[True] = True
    external_effects_simulated: Literal[True] = True
    adapter_mode: Literal["direct_prompt_contract_validated"] = "direct_prompt_contract_validated"
    research_conclusion_eligible: Literal[False] = False
    correction_of: Literal["t16c-live-reanalysis-v0.2"] = "t16c-live-reanalysis-v0.2"
    legacy_harm_semantics: Literal["selector_effect_with_receipt_not_attack_success"] = (
        "selector_effect_with_receipt_not_attack_success"
    )
    source_trial_results_path: NonEmptyStr
    source_trial_results_sha256: Sha256Hex
    source_record_count: NonNegativeInt
    raw_evidence_immutable: Literal[True] = True
    repeat_is_independent_statistical_unit: Literal[False] = False
    design_binding: LiveDesignBinding
    evidence_basis: AuditEvidenceBasis
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
    def require_closed_source_accounting(self) -> Self:
        """来源、设计和 legacy 三分类必须覆盖同一完整记录集合。"""
        total = (
            self.legacy_outcomes.harm_count
            + self.legacy_outcomes.completed_without_harm_count
            + self.legacy_outcomes.invalid_count
        )
        if total != self.source_record_count:
            self._invalid("legacy 三分类未覆盖来源记录")
        if self.provenance_not_available_count != self.source_record_count:
            self._invalid("provenance N/A 未覆盖来源记录")
        if len(self.design_binding.observed_trial_ids) != self.source_record_count:
            self._invalid("设计绑定的观察 Trial 数与来源记录不一致")
        return self

    @staticmethod
    def _invalid(detail: str) -> None:
        raise PydanticCustomError("t16c_v3_report", detail)
