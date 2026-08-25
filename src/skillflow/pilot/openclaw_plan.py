"""把受控 T12 Scenario 编译为 OpenClaw 假模型执行计划。"""

from pathlib import Path, PurePosixPath
from typing import assert_never

from skillflow.benchmark.scripted_backend import ToolScriptAction
from skillflow.benchmark.t12_fixtures import t12_fixture_registry
from skillflow.instrumentation.tool_types import (
    HttpSendArgs,
    ReadFileArgs,
    ReadMemoryArgs,
    ShellExecArgs,
    WriteMemoryArgs,
)
from skillflow.models.enums import CapabilityAction, Scope
from skillflow.models.resources import ResourceRef
from skillflow.models.scenario import Scenario
from skillflow.models.scenario_parts import ScenarioStep, StepAction
from skillflow.pilot.errors import PilotPlanError
from skillflow.pilot.openclaw_plan_models import (
    OpenClawInvocationPlan,
    OpenClawResourceFact,
    OpenClawRevocationPlan,
    OpenClawScenarioPlan,
    OpenClawSkillPlan,
    OpenClawToolCall,
    OpenClawToolName,
    OpenClawWorkspaceFile,
)
from skillflow.validation import validate_yaml_document


def compile_openclaw_plan(path: Path) -> OpenClawScenarioPlan:
    """只解释白名单 fixture；拒绝 Shell 和未知实现。"""
    scenario = validate_yaml_document(path, Scenario)
    scripts, _ = t12_fixture_registry()
    origins = tuple(f"asset:{asset.id}" for asset in scenario.assets)
    files = tuple(
        OpenClawWorkspaceFile(
            relative_path=_asset_path(asset.uri),
            content=_asset_content(asset.marker),
        )
        for asset in scenario.assets
    )
    skill_impl = {skill.id: skill.implementation.root for skill in scenario.skills}
    resources: dict[tuple[OpenClawToolName, str, str | None], OpenClawResourceFact] = {}
    invocations: list[OpenClawInvocationPlan] = []
    revocations: list[OpenClawRevocationPlan] = []
    producers: dict[str, str] = {}
    for session in scenario.sessions:
        for step in session.steps:
            if step.action is StepAction.REVOKE_SKILL and step.skill is not None:
                revocations.append(
                    OpenClawRevocationPlan(session_id=session.id, skill_id=step.skill)
                )
            elif step.action is StepAction.INVOKE_SKILL and step.skill is not None:
                try:
                    script = scripts[skill_impl[step.skill]]
                except KeyError as error:
                    raise PilotPlanError.fixture_missing(step.skill) from error
                visible_inputs = _visible_inputs(scenario, step, producers)
                calls = tuple(
                    _compile_action(action, scenario, files, origins, resources)
                    for action in script.actions
                    if _inputs_available(action, visible_inputs)
                )
                invocations.append(
                    OpenClawInvocationPlan(
                        session_id=session.id,
                        step_id=step.id,
                        skill_id=step.skill,
                        prompt=f"${step.skill} {scenario.task.prompt} step={step.id}",
                        tool_calls=calls,
                    )
                )
            for artifact_output in step.outputs:
                if step.skill is not None:
                    producers[artifact_output.alias] = step.skill
            for tool_output in step.tool_outputs:
                if step.skill is not None:
                    producers[tool_output.alias.alias] = step.skill
    return OpenClawScenarioPlan(
        scenario_id=scenario.id,
        task_id=scenario.task.id,
        run_id=f"openclaw-{scenario.id.lower()}",
        skills=tuple(OpenClawSkillPlan(skill_id=skill.id) for skill in scenario.skills),
        workspace_files=files,
        resources=tuple(resources.values()),
        invocations=tuple(invocations),
        revocations=tuple(revocations),
        target_effect_aliases=tuple(item.alias for item in scenario.effect_selectors),
        expected_origin_ids=origins,
    )


def _compile_action(
    action: ToolScriptAction,
    scenario: Scenario,
    files: tuple[OpenClawWorkspaceFile, ...],
    origins: tuple[str, ...],
    resources: dict[tuple[OpenClawToolName, str, str | None], OpenClawResourceFact],
) -> OpenClawToolCall:
    arguments = action.arguments
    match arguments:
        case ReadFileArgs(resource=resource, sensitivity=sensitivity):
            relative = _workspace_path(resource)
            alias = _selector_alias(scenario, CapabilityAction.FILE_READ, resource, _context())
            _add_resource(
                resources,
                OpenClawResourceFact(
                    tool=OpenClawToolName.READ,
                    relative_path=relative,
                    resource=resource,
                    action=CapabilityAction.FILE_READ,
                    source=resource,
                    sink=_context(),
                    scope=Scope.EXACT_FILE,
                    sensitivity=sensitivity,
                    origin_ids=origins,
                    effect_alias=alias,
                ),
            )
            return OpenClawToolCall(tool=OpenClawToolName.READ, relative_path=relative)
        case WriteMemoryArgs(key=key, source=source, sensitivity=sensitivity):
            relative = f"memory/{key}.md"
            sink = ResourceRef(f"memory:/{key}")
            _add_resource(
                resources,
                OpenClawResourceFact(
                    tool=OpenClawToolName.WRITE,
                    relative_path=relative,
                    resource=sink,
                    action=CapabilityAction.MEMORY_WRITE,
                    source=source,
                    sink=sink,
                    scope=Scope.EXACT_KEY,
                    sensitivity=sensitivity,
                    origin_ids=origins,
                ),
            )
            return OpenClawToolCall(
                tool=OpenClawToolName.WRITE,
                relative_path=relative,
                content=_single_payload(files),
            )
        case ReadMemoryArgs(key=key, sensitivity=sensitivity):
            relative = f"memory/{key}.md"
            source = ResourceRef(f"memory:/{key}")
            _add_resource(
                resources,
                OpenClawResourceFact(
                    tool=OpenClawToolName.READ,
                    relative_path=relative,
                    resource=source,
                    action=CapabilityAction.MEMORY_READ,
                    source=source,
                    sink=_context(),
                    scope=Scope.EXACT_KEY,
                    sensitivity=sensitivity,
                    origin_ids=origins,
                ),
            )
            return OpenClawToolCall(tool=OpenClawToolName.READ, relative_path=relative)
        case HttpSendArgs(source=source, sink=sink, sensitivity=sensitivity):
            alias = _selector_alias(scenario, CapabilityAction.NETWORK_SEND, source, sink)
            return OpenClawToolCall(
                tool=OpenClawToolName.SAFE_SINK,
                effect_alias=alias or action.action_id,
                action=CapabilityAction.NETWORK_SEND,
                source=source,
                sink=sink,
                sensitivity=sensitivity,
                origin_ids=origins,
            )
        case ShellExecArgs():
            raise PilotPlanError.shell_forbidden()
        case _ as unreachable:
            assert_never(unreachable)


def _add_resource(
    resources: dict[tuple[OpenClawToolName, str, str | None], OpenClawResourceFact],
    fact: OpenClawResourceFact,
) -> None:
    resources[(fact.tool, fact.relative_path, fact.effect_alias)] = fact


def _selector_alias(
    scenario: Scenario,
    action: CapabilityAction,
    source: ResourceRef | None,
    sink: ResourceRef,
) -> str | None:
    return next(
        (
            item.alias
            for item in scenario.effect_selectors
            if item.action is action and item.source_pattern == source and item.sink_pattern == sink
        ),
        None,
    )


def _visible_inputs(scenario: Scenario, step: ScenarioStep, producers: dict[str, str]) -> int:
    if scenario.harness.shared_context or step.skill is None:
        return len(step.inputs)
    return sum(producers.get(item.alias) == step.skill for item in step.inputs)


def _inputs_available(action: ToolScriptAction, input_count: int) -> bool:
    indexes = tuple(
        item.input_index
        for item in (action.input_binding, action.input_gate, action.authorization_claim)
        if item is not None
    )
    return all(index < input_count for index in indexes)


def _asset_path(resource: ResourceRef) -> str:
    root = resource.root
    if not root.startswith("fixture://"):
        raise PilotPlanError.unsupported_asset(root)
    return _safe_relative(root.removeprefix("fixture://"))


def _workspace_path(resource: ResourceRef) -> str:
    root = resource.root
    if not root.startswith("workspace:/"):
        raise PilotPlanError.unsupported_file(root)
    return _safe_relative(root.removeprefix("workspace:/"))


def _safe_relative(value: str) -> str:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise PilotPlanError.unsafe_path(value)
    return path.as_posix()


def _asset_content(marker: str | None) -> str:
    if marker is None:
        raise PilotPlanError.marker_missing()
    return marker


def _single_payload(files: tuple[OpenClawWorkspaceFile, ...]) -> str:
    if len(files) != 1:
        raise PilotPlanError.source_asset_count()
    return files[0].content


def _context() -> ResourceRef:
    return ResourceRef("context:/task")
