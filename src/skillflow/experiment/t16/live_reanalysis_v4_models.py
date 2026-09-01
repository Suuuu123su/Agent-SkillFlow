"""T16-C 0.4 设计合同与可识别下界报告模型。"""

from typing import Literal, NoReturn, Self, assert_never

from pydantic import model_validator
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
from skillflow.experiment.t16.live_reanalysis_v3_models import (
    AuditEvidenceBasis,
    LiveDesignBinding,
    NonNegativeInt,
    Sha256Hex,
)
from skillflow.models.base import NonEmptyStr, StrictModel


class PhaseContractBinding(StrictModel):
    """把未来运行绑定到单一 Phase Contract，历史记录显式报告 N/A。"""

    status: Literal["available", "not_available"]
    sha256: Sha256Hex | None = None
    reason: NonEmptyStr | None = None
    unavailable_trial_ids: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def require_closed_status(self) -> Self:
        """Available 与 not_available 的字段组合必须互斥且完整。"""
        unavailable = self.unavailable_trial_ids
        if unavailable != tuple(sorted(unavailable)) or len(set(unavailable)) != len(unavailable):
            self._invalid("phase contract N/A trial_id 必须唯一且确定排序")
        match self.status:
            case "available":
                if self.sha256 is None or self.reason is not None or unavailable:
                    self._invalid("available phase contract 必须只有单一 SHA256")
            case "not_available":
                if self.sha256 is not None or self.reason is None or not unavailable:
                    self._invalid("not_available phase contract 必须给出原因与受影响 Trial")
            case unreachable:
                assert_never(unreachable)
        return self

    @staticmethod
    def _invalid(detail: str) -> NoReturn:
        raise PydanticCustomError("t16c_v4_phase_contract", detail)


class LiveDesignBindingV4(LiveDesignBinding):
    """在 v0.3 设计绑定上加入 Phase Contract 与历史兼容限制。"""

    phase_contract: PhaseContractBinding
    compatibility_limitations: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def require_phase_limitation(self) -> Self:
        """只有历史 Phase Contract N/A 才允许设计绑定兼容限制。"""
        match self.phase_contract.status:
            case "available":
                expected = False
            case "not_available":
                expected = True
            case unreachable:
                assert_never(unreachable)
        if bool(self.compatibility_limitations) != expected:
            self._invalid_v4("Phase Contract N/A 必须同步公开兼容性限制")
        return self

    @staticmethod
    def _invalid_v4(detail: str) -> NoReturn:
        raise PydanticCustomError("t16c_v4_design_binding", detail)


class TargetExecutionAuthorizationSummaryV4(TargetExecutionAuthorizationSummary):
    """补充未分类 Trial 的首个原始 Receipt，使下界可复验。"""

    unclassified_receipt_ids: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def require_unclassified_receipts(self) -> Self:
        """每个未分类 receipted Trial 精确绑定一个唯一 Receipt。"""
        receipts = self.unclassified_receipt_ids
        if len(receipts) != self.unclassified_receipted_trial_count:
            self._invalid("未分类 Receipt 数与 Trial 数不一致")
        if len(set(receipts)) != len(receipts) or set(receipts) & set(self.receipt_ids):
            self._invalid("未分类 Receipt 必须唯一且不能进入已识别目标分区")
        return self

    @staticmethod
    def _invalid(detail: str) -> NoReturn:
        raise PydanticCustomError("t16c_v4_target_receipts", detail)


class DesignLabeledOperationalUeaV4(DesignLabeledOperationalUea):
    """为操作性 UEA 下界补充无法分类的首个原始 Receipt。"""

    unclassified_receipt_ids: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def require_unclassified_receipts(self) -> Self:
        """未分类 Trial 与 Receipt 必须逐条对应且不混入受影响分区。"""
        receipts = self.unclassified_receipt_ids
        if len(receipts) != len(self.unclassified_receipted_trial_ids):
            self._invalid("操作性 UEA 未分类 Receipt 与 Trial 数不一致")
        if len(set(receipts)) != len(receipts) or set(receipts) & set(self.receipt_ids):
            self._invalid("操作性 UEA 未分类 Receipt 分区不唯一")
        return self

    @staticmethod
    def _invalid(detail: str) -> NoReturn:
        raise PydanticCustomError("t16c_v4_operational_uea_receipts", detail)


class LiveReanalysisReportV4(StrictModel):
    """不改写 v0.3 的 T16-C 0.4 证据语义修正版报告。"""

    schema_version: Literal["0.4"] = "0.4"
    simulation_only: Literal[False] = False
    live_model: Literal[True] = True
    external_effects_simulated: Literal[True] = True
    adapter_mode: Literal["direct_prompt_contract_validated"] = "direct_prompt_contract_validated"
    research_conclusion_eligible: Literal[False] = False
    correction_of: Literal["t16c-live-reanalysis-v0.3"] = "t16c-live-reanalysis-v0.3"
    legacy_harm_semantics: Literal["selector_effect_with_receipt_not_attack_success"] = (
        "selector_effect_with_receipt_not_attack_success"
    )
    source_trial_results_path: NonEmptyStr
    source_trial_results_sha256: Sha256Hex
    source_record_count: NonNegativeInt
    raw_evidence_immutable: Literal[True] = True
    repeat_is_independent_statistical_unit: Literal[False] = False
    design_binding: LiveDesignBindingV4
    evidence_basis: AuditEvidenceBasis
    legacy_outcomes: LegacyOutcomeSummary
    hiaa: ReanalysisHiaaSummary
    authorization_operational_rates: tuple[ReanalysisConditionRate, ...]
    m2_operational_rates: tuple[ReanalysisM2SessionRate, ...]
    target_execution_authorization: TargetExecutionAuthorizationSummaryV4
    operational_design_labeled_uea: DesignLabeledOperationalUeaV4
    formal_uea: UnavailableFormalMetric
    alr: UnavailableFormalMetric
    rir_1: UnavailableFormalMetric
    rir_3: UnavailableFormalMetric
    provenance: UnavailableFormalMetric
    provenance_not_available_count: NonNegativeInt

    @model_validator(mode="after")
    def require_same_unclassified_partition(self) -> Self:
        """来源闭合，且目标执行与操作性 UEA 公开同一未分类 Receipt 分区。"""
        total = (
            self.legacy_outcomes.harm_count
            + self.legacy_outcomes.completed_without_harm_count
            + self.legacy_outcomes.invalid_count
        )
        if total != self.source_record_count:
            self._invalid_report("legacy 三分类未覆盖来源记录")
        if self.provenance_not_available_count != self.source_record_count:
            self._invalid_report("provenance N/A 未覆盖来源记录")
        if len(self.design_binding.observed_trial_ids) != self.source_record_count:
            self._invalid_report("设计绑定的观察 Trial 数与来源记录不一致")
        target = self.target_execution_authorization
        operational = self.operational_design_labeled_uea
        if (
            target.unclassified_receipted_trial_ids != operational.unclassified_receipted_trial_ids
            or target.unclassified_receipt_ids != operational.unclassified_receipt_ids
        ):
            self._invalid_report("目标执行与操作性 UEA 的未分类 Receipt 分区不一致")
        return self

    @staticmethod
    def _invalid_report(detail: str) -> NoReturn:
        raise PydanticCustomError("t16c_v4_report", detail)
