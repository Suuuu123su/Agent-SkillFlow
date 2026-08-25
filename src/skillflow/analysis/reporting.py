"""单场景风险报告与多场景 micro 聚合。"""

from skillflow.analysis.effective_authority import aggregate_uea, calculate_uea
from skillflow.analysis.facts import (
    BasicMetricsAggregation,
    ScenarioMetricCalculation,
    ScenarioMetricFacts,
)
from skillflow.analysis.provenance_metrics import (
    aggregate_provenance,
    calculate_provenance,
)
from skillflow.models.reports import RunRiskReport


def analyze_scenario(facts: ScenarioMetricFacts) -> RunRiskReport:
    """从一个场景的中立事实生成 Run 级风险报告。"""
    uea = calculate_uea(facts.effects)
    provenance = calculate_provenance(facts.provenance)
    return RunRiskReport(
        schema_version="0.1",
        report_scope="run",
        run_id=facts.run_id,
        scenario_id=facts.scenario_id,
        uea=uea.summary,
        provenance=provenance,
        unauthorized_effects=uea.unauthorized_effects,
        effect_ids=tuple(sample.effect_id for sample in facts.effects),
        authorized_flags=tuple(sample.authorized for sample in facts.effects),
        executed_decisions=tuple(sample.executed for sample in facts.effects),
        receipt_ids=tuple(sample.receipt_id for sample in facts.effects),
        evidence_event_ids=_event_evidence_ids(facts),
    )


def aggregate_scenarios(
    scenarios: tuple[ScenarioMetricFacts, ...],
) -> BasicMetricsAggregation:
    """保留逐场景结果，并按原始实例与混淆计数计算 micro。"""
    reports = tuple(analyze_scenario(scenario) for scenario in scenarios)
    uea_calculations = tuple(calculate_uea(scenario.effects) for scenario in scenarios)
    provenance_summaries = tuple(
        calculate_provenance(scenario.provenance) for scenario in scenarios
    )
    return BasicMetricsAggregation(
        scenarios=reports,
        micro=ScenarioMetricCalculation(
            uea=aggregate_uea(uea_calculations),
            provenance=aggregate_provenance(provenance_summaries),
        ),
    )


def _event_evidence_ids(facts: ScenarioMetricFacts) -> tuple[str, ...]:
    values = (
        *(
            event_id
            for sample in facts.effects
            for path in sample.paths
            for event_id in path.evidence_event_ids
        ),
        *(event_id for sample in facts.provenance for event_id in sample.evidence_event_ids),
    )
    return tuple(dict.fromkeys(values))
