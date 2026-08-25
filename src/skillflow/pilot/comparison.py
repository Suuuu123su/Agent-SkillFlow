"""T15 两个 Adapter 的平台无关比较。"""

from skillflow.pilot.errors import PilotComparisonError
from skillflow.pilot.models import PilotObservation, PilotScenarioComparison


def compare_observations(
    mock: PilotObservation,
    openclaw: PilotObservation,
) -> PilotScenarioComparison:
    """比较 Effect、来源保持率和策略事实，不填补平台缺口。"""
    if mock.scenario_id != openclaw.scenario_id:
        raise PilotComparisonError.scenario_mismatch()
    mock_policies = tuple(item.policy_fact for item in mock.target_effects)
    openclaw_policies = tuple(item.policy_fact for item in openclaw.target_effects)
    mock_value = mock.provenance_recall.value
    openclaw_value = openclaw.provenance_recall.value
    basis_match = mock.provenance_basis is openclaw.provenance_basis
    delta = (
        None
        if mock_value is None or openclaw_value is None or not basis_match
        else openclaw_value - mock_value
    )
    return PilotScenarioComparison(
        scenario_id=mock.scenario_id,
        mock_effect_count=len(mock.target_effects),
        openclaw_effect_count=len(openclaw.target_effects),
        effect_count_match=len(mock.target_effects) == len(openclaw.target_effects),
        mock_provenance_recall=mock.provenance_recall,
        openclaw_provenance_recall=openclaw.provenance_recall,
        mock_provenance_basis=mock.provenance_basis,
        openclaw_provenance_basis=openclaw.provenance_basis,
        provenance_basis_match=basis_match,
        provenance_delta=delta,
        policy_match=mock_policies == openclaw_policies,
        differences=tuple(dict.fromkeys((*mock.missing_hooks, *openclaw.missing_hooks))),
    )
