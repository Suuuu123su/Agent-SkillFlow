from pathlib import Path

from skillflow.experiment.t17.contracts import HookName
from skillflow.experiment.t17.scenario_registry import (
    T17ConditionKind,
    T17MetricName,
    expand_variant_measurements,
    load_scenario_measurement_registry,
)
from skillflow.policy.reasons import PolicyReasonCode


def test_t17_registry_expands_to_all_24_mvp_variants() -> None:
    # Given: the frozen T17 scenario registry bound to the existing MVP Matrix.
    registry = load_scenario_measurement_registry(
        Path("experiments/t17/scenario_measurements.yaml")
    )

    # When: the registry is expanded through the real Matrix and Scenario models.
    variants = expand_variant_measurements(Path(), registry)

    # Then: every core variant has one strict task/risk/Hook specification.
    assert len(registry.scenarios) == 16
    assert len(variants) == 24
    assert len({item.variant for item in variants}) == 24
    assert len({item.scenario.scenario_id for item in variants}) == 15
    assert all(HookName.TASK_SUCCESS in item.scenario.required_hooks for item in variants)
    assert all(HookName.AUTHORIZATION in item.scenario.required_hooks for item in variants)
    assert all(
        set(item.scenario.legitimate_effect_aliases).isdisjoint(item.scenario.risk_effect_aliases)
        for item in variants
    )
    assert {item.scenario.condition_kind for item in variants} == {
        T17ConditionKind.BENIGN_CONTROL,
        T17ConditionKind.RISK,
    }


def test_t17_registry_freezes_advanced_metric_and_reason_boundaries() -> None:
    # Given: the expanded real registry.
    registry = load_scenario_measurement_registry(
        Path("experiments/t17/scenario_measurements.yaml")
    )
    by_scenario = {item.scenario_id: item for item in registry.scenarios}

    # When/Then: C/A/M and Scope/Lifetime semantics are explicit, not inferred from IDs.
    assert T17MetricName.HIAA in by_scenario["C1"].applicable_metrics
    assert T17MetricName.HIAA in by_scenario["C2"].applicable_metrics
    assert T17MetricName.ALR in by_scenario["A1"].applicable_metrics
    assert T17MetricName.RIR_1 in by_scenario["M2"].applicable_metrics
    assert T17MetricName.RIR_3 in by_scenario["M2"].applicable_metrics
    assert by_scenario["S1"].expected_reason_codes == (PolicyReasonCode.RESOURCE_SCOPE_EXCEEDED,)
    assert by_scenario["L1"].expected_reason_codes == (PolicyReasonCode.CROSS_SESSION_USE,)
