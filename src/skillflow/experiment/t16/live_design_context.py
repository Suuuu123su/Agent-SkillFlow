"""T16-C 由真实 Scenario 编译的盲测能力上下文。"""

from dataclasses import dataclass

from skillflow.experiment.t16.live_design_models import (
    LiveCapabilityContext,
    LiveEffectAliasBinding,
)
from skillflow.experiment.t16.live_prompt_text import COMMON_POLICY
from skillflow.experiment.t16.live_tools import LiveToolName
from skillflow.experiment.t16.openai_response_models import JsonObject
from skillflow.experiment.t16.preregistration_models import T16Condition
from skillflow.models.authorization import AuthorizationGrant
from skillflow.models.effects import CapabilityEffect
from skillflow.models.enums import Lifetime, Scope
from skillflow.models.scenario import Scenario
from skillflow.models.scenario_parts import StepAction
from skillflow.policy.matchers import match_grants
from skillflow.policy.models import AuthorizationBoundary, GrantMatchRequest


@dataclass(frozen=True, slots=True)
class LiveEffectSelectorBindingError(ValueError):
    """Live 设计引用与实际 Scenario effect selector 不一致。"""

    scenario_id: str
    detail: str

    def __str__(self) -> str:
        """返回不含模型输入的稳定诊断。"""
        return f"{self.scenario_id}: {self.detail}"


@dataclass(frozen=True, slots=True)
class LiveTargetGrantMatchIndeterminateError(ValueError):
    """预注册静态 Scenario 缺少证明完整 Grant 匹配所需的事实。"""

    scenario_id: str
    detail: str

    def __str__(self) -> str:
        """明确拒绝把静态设计事实冒充运行期确认。"""
        return (
            f"{self.scenario_id}: 预注册静态 Scenario Grant 结构匹配不可判定："
            f"{self.detail}；这不是运行期 Hook 或已观察到的交互确认"
        )


def capability_context(
    scenario: Scenario,
    session_index: int,
    tool_names: tuple[LiveToolName, ...],
    asset_ids: tuple[str, ...],
    effect_alias_bindings: tuple[LiveEffectAliasBinding, ...] = (),
) -> LiveCapabilityContext:
    """公开当前 Session 已出现的真实 Grant 与能力事实，不附加结论。"""
    step_grants = tuple(
        step.grant
        for index, session in enumerate(scenario.sessions)
        if index <= session_index
        for step in session.steps
        if step.grant is not None
    )
    selectors_by_alias = {item.alias: item for item in scenario.effect_selectors}
    public_selectors = []
    for binding in effect_alias_bindings:
        selector = selectors_by_alias.get(binding.actual_alias)
        if selector is None:
            raise LiveEffectSelectorBindingError(
                scenario.id,
                f"未声明 effect selector: {binding.actual_alias}",
            )
        public_selectors.append(selector.model_copy(update={"alias": binding.public_alias}))
    return LiveCapabilityContext(
        session_index=session_index,
        skill_ids=tuple(item.id for item in scenario.skills),
        asset_ids=asset_ids,
        tool_names=tool_names,
        grants=(*scenario.grants, *step_grants),
        effect_selectors=tuple(public_selectors),
    )


def single_effect_alias(scenario: Scenario) -> str:
    """返回唯一实际 selector，拒绝静默挑选。"""
    aliases = tuple(item.alias for item in scenario.effect_selectors)
    if len(aliases) != 1:
        raise LiveEffectSelectorBindingError(
            scenario.id,
            "Live 设计要求精确声明一个 effect selector",
        )
    return aliases[0]


def condition_effect_alias(condition: T16Condition, scenario: Scenario) -> str:
    """把条件 harm selector 绑定到实际 Scenario。"""
    if condition.harm_selector is None:
        return single_effect_alias(scenario)
    return known_effect_alias(scenario, condition.harm_selector.alias)


def known_effect_alias(scenario: Scenario, alias: str) -> str:
    """拒绝 Live 程序引用 Scenario 未声明的 selector。"""
    if alias not in {item.alias for item in scenario.effect_selectors}:
        raise LiveEffectSelectorBindingError(
            scenario.id,
            f"未声明 effect selector: {alias}",
        )
    return alias


def has_matching_target_grant(
    scenario: Scenario,
    aliases: tuple[str, ...],
    *,
    revoked_grant_ids: frozenset[str] = frozenset(),
) -> bool:
    """证明预注册静态 Scenario 中存在完整匹配 Grant。

    Live 安全 Effect 是一次精确 sink 的 Tool 调用，因此请求固定为
    ``scope=exact-sink``、``lifetime=call``、``sensitivity=0``。目标 grantee
    只能由 Scenario 全序中的 terminal ``invoke_skill`` 唯一给出；边界来自
    Scenario task、该 Session 与静态虚拟时钟。只纳入目标调用前已经出现的
    step Grant，避免把未来 ``user_confirm`` 预加载为授权。

    该结论只描述预注册静态 Scenario 结构，不是运行期 Hook 事实，也不表示
    实际发生了交互确认。Scenario DSL 当前不能声明 AUTH_REVOKE；调用方若有
    外部静态撤销事实，必须通过 ``revoked_grant_ids`` 显式提供。call lifetime
    需要真实 call_id，静态设计无法观察时会结构化拒绝，而不会猜测。
    """
    if len(aliases) != 1:
        raise LiveTargetGrantMatchIndeterminateError(
            scenario.id,
            "必须精确指定一个目标 effect selector",
        )
    selector_alias = known_effect_alias(scenario, aliases[0])
    selector = next(item for item in scenario.effect_selectors if item.alias == selector_alias)
    session_index, step_index, grantee_id = _terminal_invocation(scenario)
    grants = _static_grants_before_target(scenario, session_index, step_index)
    effect = CapabilityEffect(
        source=selector.source_pattern,
        action=selector.action,
        sink=selector.sink_pattern,
        scope=Scope.EXACT_SINK,
        lifetime=Lifetime.CALL,
        sensitivity=0,
    )
    boundary = AuthorizationBoundary(
        task_id=scenario.task.id,
        session_id=scenario.sessions[session_index].id,
        call_id="static-call-id-unavailable",
        effect_time=scenario.clock.start,
    )
    request = GrantMatchRequest(
        actor_id=grantee_id,
        effect=effect,
        boundary=boundary,
        revoked_grant_ids=revoked_grant_ids,
    )
    non_call_grants = tuple(grant for grant in grants if grant.lifetime is not Lifetime.CALL)
    if match_grants(non_call_grants, request).matched_grant_ids:
        return True

    for grant in grants:
        if grant.lifetime is not Lifetime.CALL or grant.call_id is None:
            continue
        observed_call_hypothesis = GrantMatchRequest(
            actor_id=grantee_id,
            effect=effect,
            boundary=AuthorizationBoundary(
                task_id=boundary.task_id,
                session_id=boundary.session_id,
                call_id=grant.call_id,
                effect_time=boundary.effect_time,
            ),
            revoked_grant_ids=revoked_grant_ids,
        )
        if match_grants((grant,), observed_call_hypothesis).matched_grant_ids:
            raise LiveTargetGrantMatchIndeterminateError(
                scenario.id,
                f"call lifetime Grant {grant.grant_id} 缺少真实 call_id",
            )
    return False


def _terminal_invocation(scenario: Scenario) -> tuple[int, int, str]:
    invocations = tuple(
        (session_index, step_index, step.skill)
        for session_index, session in enumerate(scenario.sessions)
        for step_index, step in enumerate(session.steps)
        if step.action is StepAction.INVOKE_SKILL
    )
    if not invocations:
        raise LiveTargetGrantMatchIndeterminateError(
            scenario.id,
            "Scenario 没有 terminal invoke_skill，无法确定目标 grantee",
        )
    session_index, step_index, grantee_id = invocations[-1]
    if grantee_id is None:
        raise LiveTargetGrantMatchIndeterminateError(
            scenario.id,
            "terminal invoke_skill 未声明 Skill，无法确定目标 grantee",
        )
    return session_index, step_index, grantee_id


def _static_grants_before_target(
    scenario: Scenario,
    target_session_index: int,
    target_step_index: int,
) -> tuple[AuthorizationGrant, ...]:
    step_grants = tuple(
        step.grant
        for session_index, session in enumerate(scenario.sessions)
        for step_index, step in enumerate(session.steps)
        if (session_index, step_index) < (target_session_index, target_step_index)
        and step.grant is not None
    )
    return (*scenario.grants, *step_grants)


def model_input_messages(
    context: LiveCapabilityContext,
    skill: str,
    task: str,
) -> tuple[JsonObject, ...]:
    """将事实上下文、Skill 与任务分层为模型输入。"""
    return (
        {"role": "developer", "content": [{"type": "input_text", "text": COMMON_POLICY}]},
        {
            "role": "developer",
            "content": [{"type": "input_text", "text": context.model_dump_json()}],
        },
        {"role": "developer", "content": [{"type": "input_text", "text": skill}]},
        {"role": "user", "content": [{"type": "input_text", "text": task}]},
    )
