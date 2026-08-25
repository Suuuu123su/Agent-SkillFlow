"""按 report_scope 判别的风险报告数据契约。"""

from typing import Annotated, Literal

from pydantic import Field, TypeAdapter

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


class ReplayRiskReport(StrictModel):
    """一次原始/中和 Run 配对的因果影响报告。"""

    schema_version: NonEmptyStr
    report_scope: Literal["replay"]
    replay_id: NonEmptyStr
    original_run_id: NonEmptyStr
    neutral_run_id: NonEmptyStr
    intervention_artifact_id: NonEmptyStr
    observed_effect_ids: tuple[NonEmptyStr, ...] = ()
    ci: UnitInterval
    confirmed_influence_edges: tuple[tuple[NonEmptyStr, NonEmptyStr], ...] = ()


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
