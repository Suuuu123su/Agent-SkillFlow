"""按 report_scope 判别的风险报告数据契约。"""

from typing import Annotated, Literal, Self

from pydantic import Field, TypeAdapter, model_validator
from pydantic_core import PydanticCustomError

from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.enums import Decision
from skillflow.models.metrics import (
    ProvenanceMetricSummary,
    UeaMetricSummary,
    UnauthorizedEffectEvidence,
)
from skillflow.models.references import ScenarioPath

UnitInterval = Annotated[float, Field(ge=0.0, le=1.0)]
NonNegativeInt = Annotated[int, Field(ge=0)]
NonNegativeFloat = Annotated[float, Field(ge=0.0)]


class RunRiskReport(StrictModel):
    """单次 Run 的结果与可审计证据索引。"""

    schema_version: NonEmptyStr
    report_scope: Literal["run"]
    run_id: NonEmptyStr
    scenario_id: NonEmptyStr
    experiment_id: NonEmptyStr | None = None
    scenario: ScenarioPath | None = None
    variant: NonEmptyStr | None = None
    seed: int | None = None
    backend: NonEmptyStr | None = None
    task_success: bool | None = None
    harm: bool | None = None
    uea: UeaMetricSummary
    provenance: ProvenanceMetricSummary
    unauthorized_effects: tuple[UnauthorizedEffectEvidence, ...]
    latency_ms: NonNegativeFloat | None = None
    effect_ids: tuple[NonEmptyStr, ...] = ()
    authorized_flags: tuple[bool, ...] = ()
    baseline_decisions: tuple[Decision, ...] = ()
    policy_decisions: tuple[Decision, ...] = ()
    executed_decisions: tuple[bool, ...] = ()
    receipt_ids: tuple[NonEmptyStr, ...] = ()
    evidence_event_ids: tuple[NonEmptyStr, ...] = ()


class ConfirmedInfluenceEdge(StrictModel):
    """仅由成对反事实证据确认的 Artifact→Effect 影响边。"""

    source_artifact_id: NonEmptyStr
    target_effect_id: NonEmptyStr
    relation: Literal["INFLUENCE_CONFIRMED"] = "INFLUENCE_CONFIRMED"


class ReplayRiskReport(StrictModel):
    """一次原始/中和 Run 配对的因果影响报告。"""

    schema_version: NonEmptyStr
    report_scope: Literal["replay"]
    replay_id: NonEmptyStr
    original_run_id: NonEmptyStr
    neutral_run_id: NonEmptyStr
    intervention_artifact_id: NonEmptyStr
    original_intervention_artifact_id: NonEmptyStr
    neutral_intervention_artifact_id: NonEmptyStr
    observed_effect_ids: tuple[NonEmptyStr, ...] = ()
    original_effect_ids: tuple[NonEmptyStr, ...] = ()
    neutral_effect_ids: tuple[NonEmptyStr, ...] = ()
    removed_effect_ids: tuple[NonEmptyStr, ...] = ()
    added_effect_ids: tuple[NonEmptyStr, ...] = ()
    y_original: bool
    y_neutral: bool
    ci: Literal[-1, 0, 1]
    confirmed_influence_edges: tuple[ConfirmedInfluenceEdge, ...] = ()

    @model_validator(mode="after")
    def validate_pair_evidence(self) -> Self:
        """拒绝与两分支 Effect 集合不一致的 CI 或确认边。"""
        if self.original_run_id == self.neutral_run_id:
            self._invalid("原始与中和分支必须使用不同 run_id")
        if self.y_original is not bool(self.original_effect_ids):
            self._invalid("y_original 必须等于原始分支是否存在 Effect")
        if self.y_neutral is not bool(self.neutral_effect_ids):
            self._invalid("y_neutral 必须等于中和分支是否存在 Effect")
        if self.ci != int(self.y_original) - int(self.y_neutral):
            self._invalid("CI 必须等于 y_original - y_neutral")

        observed = tuple(dict.fromkeys((*self.original_effect_ids, *self.neutral_effect_ids)))
        removed = tuple(
            item for item in self.original_effect_ids if item not in self.neutral_effect_ids
        )
        added = tuple(
            item for item in self.neutral_effect_ids if item not in self.original_effect_ids
        )
        if self.observed_effect_ids != observed:
            self._invalid("observed_effect_ids 必须是两分支 Effect 的有序并集")
        if self.removed_effect_ids != removed or self.added_effect_ids != added:
            self._invalid("Effect diff 必须由两分支集合机械计算")

        edge_targets = tuple(edge.target_effect_id for edge in self.confirmed_influence_edges)
        expected_targets = removed if self.ci == 1 else added if self.ci == -1 else ()
        if edge_targets != expected_targets:
            self._invalid("确认影响边必须且只能指向 CI 对应的差异 Effect")
        if any(
            edge.source_artifact_id != self.intervention_artifact_id
            for edge in self.confirmed_influence_edges
        ):
            self._invalid("确认影响边必须从被干预 Artifact 出发")
        return self

    @staticmethod
    def _invalid(detail: str) -> None:
        raise PydanticCustomError("replay_evidence_inconsistent", detail)


class RawCounts(StrictModel):
    """聚合指标的原始可复核计数。"""

    run_count: NonNegativeInt
    replay_count: NonNegativeInt
    unauthorized_executed_count: NonNegativeInt
    implicit_authorization_liability_count: NonNegativeInt


class ExperimentRiskReport(StrictModel):
    """Experiment 层的四格与持续风险聚合报告。"""

    schema_version: NonEmptyStr
    report_scope: Literal["experiment"]
    experiment_id: NonEmptyStr
    run_ids: tuple[NonEmptyStr, ...]
    replay_ids: tuple[NonEmptyStr, ...]
    raw_counts: RawCounts
    p00: UnitInterval
    p01: UnitInterval
    p10: UnitInterval
    p11: UnitInterval
    hiaa_pot: UnitInterval = Field(alias="HIAA_pot")
    hiaa_run: UnitInterval = Field(alias="HIAA_run")
    alr_numerator: NonNegativeInt
    alr_denominator: NonNegativeInt
    rir_1_numerator: NonNegativeInt
    rir_1_denominator: NonNegativeInt
    rir_3_numerator: NonNegativeInt
    rir_3_denominator: NonNegativeInt


RiskReport = Annotated[
    RunRiskReport | ReplayRiskReport | ExperimentRiskReport,
    Field(discriminator="report_scope"),
]
RISK_REPORT_ADAPTER: TypeAdapter[RiskReport] = TypeAdapter(RiskReport)
