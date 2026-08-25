from skillflow.analysis.facts import (
    EffectMetricSample,
    ProvenanceSample,
    ScenarioMetricFacts,
)
from skillflow.analysis.reporting import aggregate_scenarios
from skillflow.graph.models import BoundaryDepth
from skillflow.models.effects import CapabilityEffect
from skillflow.models.enums import CapabilityAction, Lifetime, Scope
from skillflow.models.metrics import EffectPathEvidence
from skillflow.models.resources import ResourceRef


def unauthorized_effect(suffix: str) -> EffectMetricSample:
    return EffectMetricSample(
        effect_id=f"effect-{suffix}",
        receipt_id=f"receipt-{suffix}",
        decision_id=f"decision-{suffix}",
        effect=CapabilityEffect(
            source=ResourceRef("context:/task"),
            action=CapabilityAction.NETWORK_SEND,
            sink=ResourceRef("mock://external"),
            scope=Scope.EXACT_SINK,
            lifetime=Lifetime.CALL,
            sensitivity=4,
        ),
        executed=True,
        authorized=False,
        manifest_declared=True,
        matched_grant_ids=(),
        paths=(
            EffectPathEvidence(
                node_ids=("principal:skill", f"effect:effect-{suffix}"),
                evidence_event_ids=(f"event-{suffix}",),
                boundary_depth=BoundaryDepth(
                    context=0,
                    memory=0,
                    session=0,
                    skill=1,
                    tool=0,
                    total=1,
                ),
            ),
        ),
    )


def test_micro_aggregation_pools_counts_and_keeps_per_scenario_results() -> None:
    # Given: 两个场景各有一个相同 UEA 类型，来源 Precision 分别为 1 与 0
    scenario_a = ScenarioMetricFacts(
        scenario_id="scenario-a",
        run_id="run-a",
        effects=(unauthorized_effect("a"),),
        provenance=(
            ProvenanceSample(
                artifact_id="artifact-a",
                boundary_depth=0,
                observed_origins=frozenset({"A"}),
                oracle_origins=frozenset({"A"}),
            ),
        ),
    )
    scenario_b = ScenarioMetricFacts(
        scenario_id="scenario-b",
        run_id="run-b",
        effects=(unauthorized_effect("b"),),
        provenance=(
            ProvenanceSample(
                artifact_id="artifact-b",
                boundary_depth=0,
                observed_origins=frozenset(f"C{index}" for index in range(9)),
                oracle_origins=frozenset(),
            ),
        ),
    )

    # When: 汇总两个场景
    result = aggregate_scenarios((scenario_a, scenario_b))

    # Then: 保留两份 Run 报告，UEA 实例求和而类型全局去重
    assert tuple(report.scenario_id for report in result.scenarios) == (
        "scenario-a",
        "scenario-b",
    )
    assert result.micro.uea.summary.uea_count == 2
    assert result.micro.uea.summary.uea_type_count == 1

    # And: micro Precision=1/(1+9)，不是两个场景比例的算术平均
    assert result.micro.provenance.overall.precision.numerator == 1
    assert result.micro.provenance.overall.precision.denominator == 10
    assert result.micro.provenance.overall.precision.value == 0.1
