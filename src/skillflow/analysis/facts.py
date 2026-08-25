"""T09 纯指标计算使用的冻结中立事实。"""

from dataclasses import dataclass

from skillflow.models.effects import CapabilityEffect
from skillflow.models.metrics import (
    EffectPathEvidence,
    ProvenanceMetricSummary,
    UeaMetricSummary,
    UnauthorizedEffectEvidence,
)
from skillflow.models.reports import RunRiskReport


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
