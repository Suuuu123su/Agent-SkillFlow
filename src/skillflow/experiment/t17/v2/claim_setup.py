"""冻结并再次验证授权声明规格，不读取任何实验输出。"""

from skillflow.experiment.t17.v2.catalog_models import SkillBundle
from skillflow.experiment.t17.v2.claim_models import ClaimActionSpec
from skillflow.instrumentation.tool_effects import normalize_tool_request
from skillflow.models.scenario import Scenario


def claim_specs(scenario: Scenario, bundle: SkillBundle) -> tuple[ClaimActionSpec, ...]:
    """只登记真正带授权声明绑定的工具动作，标签不参与。"""
    return tuple(
        ClaimActionSpec(
            actor_id=skill.id,
            action_id=action.action_id,
            input_index=action.authorization_claim.input_index,
            expected_content_hash=action.authorization_claim.expected_content_hash,
            requested_effect=normalize_tool_request(action.arguments).effect,
        )
        for skill in scenario.skills
        for action in bundle.scripts[skill.implementation.root].actions
        if action.authorization_claim is not None
    )
