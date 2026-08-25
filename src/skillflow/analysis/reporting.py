"""单场景风险报告与多场景 micro 聚合。"""

from skillflow.analysis.effective_authority import aggregate_uea, calculate_uea
from skillflow.analysis.errors import AnalysisInvariantError
from skillflow.analysis.facts import (
    BasicMetricsAggregation,
    EffectMetricSample,
    ScenarioMetricCalculation,
    ScenarioMetricFacts,
)
from skillflow.analysis.provenance_metrics import (
    aggregate_provenance,
    calculate_provenance,
)
from skillflow.models.reports import RunRiskReport
from skillflow.models.run_results import RunEffectResult


def analyze_scenario(facts: ScenarioMetricFacts) -> RunRiskReport:
    """从一个场景的中立事实生成 Run 级风险报告。"""
    uea = calculate_uea(facts.effects)
    provenance = calculate_provenance(facts.provenance)
    effects = tuple(
        result
        for sample in facts.effects
        if (result := _standard_effect_result(sample)) is not None
    )
    metadata = facts.metadata
    harm_effects = tuple(
        item
        for item in effects
        if metadata.harm_selector is not None
        and metadata.harm_selector.alias in item.selector_aliases
    )
    return RunRiskReport(
        schema_version="0.1",
        report_scope="run",
        run_id=facts.run_id,
        scenario_id=facts.scenario_id,
        experiment_id=metadata.experiment_id,
        scenario=metadata.scenario,
        variant=metadata.variant,
        seed=metadata.seed,
        backend=metadata.backend,
        task_success=facts.task_success,
        harm=None if metadata.harm_selector is None else bool(harm_effects),
        uea=uea.summary,
        provenance=provenance,
        unauthorized_effects=uea.unauthorized_effects,
        effect_ids=tuple(sample.effect_id for sample in facts.effects),
        authorized_flags=tuple(sample.authorized for sample in facts.effects),
        baseline_decisions=tuple(item.baseline_result for item in effects),
        policy_decisions=tuple(item.policy_result for item in effects),
        executed_decisions=tuple(sample.executed for sample in facts.effects),
        receipt_ids=tuple(sample.receipt_id for sample in facts.effects),
        evidence_event_ids=_event_evidence_ids(facts),
        latency_ms=metadata.latency_ms,
        source_to_sink_paths=tuple(path for sample in facts.effects for path in sample.paths),
        effects=effects,
        counterfactual_artifacts=facts.counterfactual_artifacts,
        revocations=facts.revocations,
        rir_check_offsets=facts.rir_check_offsets,
        harm_selector=metadata.harm_selector,
        harm_effect_ids=tuple(item.effect_id for item in harm_effects),
        harm_receipt_ids=tuple(item.receipt_id for item in harm_effects),
        hiaa_cell=metadata.hiaa_cell,
        hiaa_design_id=metadata.hiaa_design_id,
        pair_id=metadata.pair_id,
        run_role=metadata.run_role,
        skill_state=metadata.skill_state,
        session_condition=metadata.session_condition,
        authorization_condition=metadata.authorization_condition,
        shared_context=metadata.shared_context,
        persistent_memory=metadata.persistent_memory,
        auto_approve_tools=metadata.auto_approve_tools,
        enforcement_mode=metadata.enforcement_mode,
        provenance_mode=metadata.provenance_mode,
        implicit_text_authorization=metadata.implicit_text_authorization,
        redacted=metadata.redacted,
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


def _standard_effect_result(sample: EffectMetricSample) -> RunEffectResult | None:
    required = (
        sample.action_id,
        sample.request_event_id,
        sample.actor_id,
        sample.session_id,
        sample.session_index,
        sample.timestamp,
        sample.baseline_result,
        sample.policy_result,
    )
    if all(value is None for value in required):
        return None
    if any(value is None for value in required):
        raise AnalysisInvariantError(
            "analyze_scenario",
            f"标准 RunResult 的 Effect 证据不完整：{sample.effect_id}",
        )
    action_id = sample.action_id
    request_event_id = sample.request_event_id
    actor_id = sample.actor_id
    session_id = sample.session_id
    session_index = sample.session_index
    timestamp = sample.timestamp
    baseline_result = sample.baseline_result
    policy_result = sample.policy_result
    if (
        action_id is None
        or request_event_id is None
        or actor_id is None
        or session_id is None
        or session_index is None
        or timestamp is None
        or baseline_result is None
        or policy_result is None
    ):
        raise AnalysisInvariantError(
            "analyze_scenario",
            f"标准 RunResult 的 Effect 类型窄化失败：{sample.effect_id}",
        )
    return RunEffectResult(
        effect_id=sample.effect_id,
        effect_alias=sample.effect_alias,
        selector_aliases=sample.selector_aliases,
        action_id=action_id,
        request_event_id=request_event_id,
        decision_id=sample.decision_id,
        actor_id=actor_id,
        session_id=session_id,
        session_index=session_index,
        timestamp=timestamp,
        effect=sample.effect,
        authorized=sample.authorized,
        baseline_result=baseline_result,
        policy_result=policy_result,
        executed=sample.executed,
        receipt_id=sample.receipt_id,
        decision_basis_artifacts=sample.decision_basis_artifacts,
        matched_grant_ids=sample.matched_grant_ids,
        reason_codes=sample.reason_codes,
    )
