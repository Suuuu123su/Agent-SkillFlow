"""T10 Artifact 输入顺序与中和策略的 Scenario 边界。"""

import pytest
from pydantic import ValidationError

from skillflow.models.scenario import Scenario
from tests.unit.models.test_scenario import valid_scenario_payload


def test_scenario_accepts_only_artifact_inputs_produced_by_an_earlier_step() -> None:
    payload = valid_scenario_payload()
    sessions = payload["sessions"]
    assert isinstance(sessions, list)
    session = sessions[0]
    assert isinstance(session, dict)
    steps = session["steps"]
    assert isinstance(steps, list)
    steps.append(
        {
            "id": "step-2",
            "action": "invoke_skill",
            "skill": "skill-a",
            "inputs": ["artifact:skill-output"],
            "outputs": ["artifact:second-output"],
        }
    )

    scenario = Scenario.model_validate(payload)

    assert scenario.sessions[0].steps[1].inputs[0].alias == "skill-output"


def test_scenario_rejects_a_future_artifact_input() -> None:
    payload = valid_scenario_payload()
    sessions = payload["sessions"]
    assert isinstance(sessions, list)
    session = sessions[0]
    assert isinstance(session, dict)
    steps = session["steps"]
    assert isinstance(steps, list)
    first = steps[0]
    assert isinstance(first, dict)
    first["inputs"] = ["artifact:future-output"]
    steps.append(
        {
            "id": "step-2",
            "action": "invoke_skill",
            "skill": "skill-a",
            "outputs": ["artifact:future-output"],
        }
    )

    with pytest.raises(ValidationError, match="此前步骤"):
        Scenario.model_validate(payload)


def test_counterfactual_rejects_skill_deletion_as_neutralization() -> None:
    payload = valid_scenario_payload()
    counterfactuals = payload["counterfactuals"]
    assert isinstance(counterfactuals, list)
    counterfactual = counterfactuals[0]
    assert isinstance(counterfactual, dict)
    counterfactual["intervention"] = "delete_skill"

    with pytest.raises(ValidationError):
        Scenario.model_validate(payload)
