"""T09 纯指标计算使用的冻结中立事实。"""

from dataclasses import dataclass
from datetime import datetime

from skillflow.models.effects import CapabilityEffect
from skillflow.models.enums import Decision, EnforcementMode, ProvenanceMode
from skillflow.models.matrix_axes import (
    AuthorizationCondition,
    MatrixRunRole,
    SessionCondition,
    SkillStateCondition,
)
from skillflow.models.matrix_design import HiaaCell
from skillflow.models.metrics import (
    EffectPathEvidence,
    ProvenanceMetricSummary,
    UeaMetricSummary,
    UnauthorizedEffectEvidence,
)
from skillflow.models.references import ScenarioPath
from skillflow.models.reports import RunRiskReport
from skillflow.models.run_results import (
    ArtifactAliasEvidence,
    DecisionBasisArtifact,
    RunRevocationEvidence,
)
from skillflow.models.scenario_parts import EffectSelector


@dataclass(frozen=True, slots=True)
class RunReportMetadata:
    """RunResult 的实验身份与矩阵控制轴。"""

    experiment_id: str | None = None
    scenario: ScenarioPath | None = None
    variant: str | None = None
    seed: int | None = None
    backend: str | None = None
    latency_ms: float | None = None
    harm_selector: EffectSelector | None = None
    hiaa_cell: HiaaCell | None = None
    hiaa_design_id: str | None = None
    pair_id: str | None = None
    run_role: MatrixRunRole = MatrixRunRole.CORE
    skill_state: SkillStateCondition = SkillStateCondition.NORMAL
    session_condition: SessionCondition = SessionCondition.ORIGINAL
    authorization_condition: AuthorizationCondition = AuthorizationCondition.NONE
    shared_context: bool | None = None
    persistent_memory: bool | None = None
    auto_approve_tools: bool | None = None
    enforcement_mode: EnforcementMode | None = None
    provenance_mode: ProvenanceMode | None = None
    implicit_text_authorization: bool | None = None
    redacted: bool = True


@dataclass(frozen=True, slots=True)
class EffectMetricSample:
    """一个 Effect/Receipt 实例的 Oracle 授权与路径事实。"""

    effect_id: str
    receipt_id: str
    decision_id: str
    effect: CapabilityEffect
    executed: bool
    authorized: bool
    manifest_declared: bool
    matched_grant_ids: tuple[str, ...]
    paths: tuple[EffectPathEvidence, ...] = ()
    effect_alias: str | None = None
    selector_aliases: tuple[str, ...] = ()
    action_id: str | None = None
    request_event_id: str | None = None
    actor_id: str | None = None
    session_id: str | None = None
    session_index: int | None = None
    timestamp: datetime | None = None
    baseline_result: Decision | None = None
    policy_result: Decision | None = None
    decision_basis_artifacts: tuple[DecisionBasisArtifact, ...] = ()
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProvenanceSample:
    """一个 Artifact 在指定边界深度上的双轨来源集合。"""

    artifact_id: str
    boundary_depth: int
    observed_origins: frozenset[str]
    oracle_origins: frozenset[str]
    evidence_event_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class UeaCalculation:
    """UEA 汇总和逐实例证据的成对结果。"""

    summary: UeaMetricSummary
    unauthorized_effects: tuple[UnauthorizedEffectEvidence, ...]


@dataclass(frozen=True, slots=True)
class ScenarioMetricFacts:
    """生成一个 RunRiskReport 所需的全部中立分析事实。"""

    scenario_id: str
    run_id: str
    effects: tuple[EffectMetricSample, ...]
    provenance: tuple[ProvenanceSample, ...]
    task_success: bool | None = None
    metadata: RunReportMetadata = RunReportMetadata()
    counterfactual_artifacts: tuple[ArtifactAliasEvidence, ...] = ()
    revocations: tuple[RunRevocationEvidence, ...] = ()
    rir_check_offsets: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class ScenarioMetricCalculation:
    """单场景两类基础指标的纯计算结果。"""

    uea: UeaCalculation
    provenance: ProvenanceMetricSummary


@dataclass(frozen=True, slots=True)
class BasicMetricsAggregation:
    """逐场景 Run 报告与从原始计数汇总的 micro 结果。"""

    scenarios: tuple[RunRiskReport, ...]
    micro: ScenarioMetricCalculation
