"""在读取技能内容前，从正常任务和固定工具依赖编译可信计划。"""

from skillflow.benchmark.scripted_backend import FixtureScript, ToolScriptAction
from skillflow.defense.task_plan import TaskNode, TrustedTaskPlan
from skillflow.experiment.t17.minimal.contracts import NormalTaskContract
from skillflow.instrumentation.tool_effects import normalize_tool_request
from skillflow.models.effects import CapabilityEffect
from skillflow.models.scenario import Scenario
from skillflow.models.scenario_parts import EffectSelector
from skillflow.models.tool_calls import ReadMemoryArgs, WriteMemoryArgs


def matches(effect: CapabilityEffect, selector: EffectSelector) -> bool:
    """本地固定目录只允许精确资源，不隐含扩大匹配范围。"""
    return (
        effect.action == selector.action
        and effect.source == selector.source_pattern
        and effect.sink == selector.sink_pattern
    )


def compile_task_plan(
    scenario: Scenario, scripts: dict[str, FixtureScript], task: NormalTaskContract
) -> TrustedTaskPlan:
    """计划来自正常产物依赖和合法效果；固定输出不授权同一步的附带动作。"""
    implementations = {s.id: s.implementation.root for s in scenario.skills}
    steps = tuple((session.id, step) for session in scenario.sessions for step in session.steps)
    actions = {
        step.id: scripts[implementations[step.skill]].actions
        for _, step in steps
        if step.skill is not None and step.skill in implementations
    }
    selected: set[tuple[str, str]] = set()
    needed = {a.alias for a in task.artifacts}
    for session_id, step in steps:
        for action in actions.get(step.id, ()):
            effect = normalize_tool_request(action.arguments).effect
            if any(
                r.session_id == session_id and matches(effect, r.selector) for r in task.effects
            ) and not any(
                _same_action(a, action)
                for sid, aid in selected
                for a in actions[sid]
                if a.action_id == aid
            ):
                selected.add((step.id, action.action_id))
    previous: tuple[frozenset[str], frozenset[tuple[str, str]]] | None = None
    while previous != (frozenset(needed), frozenset(selected)):
        previous = frozenset(needed), frozenset(selected)
        for _, step in reversed(steps):
            outputs = {a.alias for a in step.outputs} | {a.alias.alias for a in step.tool_outputs}
            if outputs & needed or any(sid == step.id for sid, _ in selected):
                needed.update(a.alias for a in step.inputs)
            selected.update(
                (step.id, a.action_id) for a in step.tool_outputs if a.alias.alias in needed
            )
        reads = {
            a.arguments.key
            for sid, aid in selected
            for a in actions.get(sid, ())
            if a.action_id == aid and isinstance(a.arguments, ReadMemoryArgs)
        }
        selected.update(
            (step.id, a.action_id)
            for _, step in steps
            for a in actions.get(step.id, ())
            if isinstance(a.arguments, WriteMemoryArgs) and a.arguments.key in reads and step.inputs
        )
    nodes: list[TaskNode] = []
    for session_id, step in steps:
        for action in actions.get(step.id, ()):
            if (step.id, action.action_id) not in selected or step.skill is None:
                continue
            nodes.append(
                TaskNode.model_validate(
                    {
                        "node_id": step.id + ":" + action.action_id,
                        "actor_id": step.skill,
                        "session_id": session_id,
                        "effect": normalize_tool_request(action.arguments).effect,
                        "predecessor_ids": (nodes[-1].node_id,) if nodes else (),
                        "parameter_schema_id": action.arguments.kind.value,
                    }
                )
            )
    return TrustedTaskPlan(plan_id="trusted-task:" + scenario.task.id, nodes=tuple(nodes))


def _same_action(left: ToolScriptAction, right: ToolScriptAction) -> bool:
    return left.action_id == right.action_id and left.arguments == right.arguments
