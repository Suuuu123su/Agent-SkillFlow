"""把拒绝、未调用和无效模型输出转换成可评估的正常运行事实。"""

from collections.abc import Mapping
from dataclasses import replace

from pydantic import ValidationError

from skillflow.benchmark.scripted_backend import (
    FixtureScript,
    ScriptedBackend,
    ScriptedInvocation,
    ScriptedInvocationResult,
    ToolScriptAction,
)
from skillflow.experiment.t17.reference_backend import (
    ReferenceModelClient,
    ReferenceModelDecision,
    ReferenceModelRequest,
    ReferenceRunContext,
)
from skillflow.experiment.t17.v2.api_models import BoundReferenceClient, CallIdentity
from skillflow.experiment.t17.v2.runtime_models import (
    DecisionFact,
    ExecutionIssue,
    ModelBehavior,
    ModelOutcomeError,
    RunCapture,
)
from skillflow.instrumentation.errors import FixtureNotFoundError
from skillflow.models.tool_calls import ReadMemoryArgs
from skillflow.store.event_store import EventStore


class V2ReferenceBackend:
    """模型不能提供真值或执行任意工具，实际副作用仍由白名单运行时签发。"""

    def __init__(
        self,
        scripts: Mapping[str, FixtureScript],
        client: ReferenceModelClient,
        context: ReferenceRunContext,
        capture: RunCapture,
        store: EventStore,
    ) -> None:
        """所有输入来自冻结配置与当前 Run，禁止跨运行查询。"""
        self._scripts = dict(scripts)
        self._client = client
        self._context = context
        self._capture = capture
        self._store = store

    def invoke(self, invocation: ScriptedInvocation) -> ScriptedInvocationResult:
        """先记录模型结果，再执行可满足前提的动作；不补采失败输出。"""
        key = invocation.implementation.root
        script = self._scripts.get(key)
        if script is None:
            raise FixtureNotFoundError(key)
        allowed = {a.action_id: a for a in script.actions}
        request = ReferenceModelRequest(
            invocation.implementation,
            invocation.inputs,
            tuple(allowed),
            self._context.scenario_id,
            self._context.task_prompt,
            script.output.decode(),
        )
        capture = self._capture
        if invocation.actor.call_id is None:
            raise ValueError("v2_model_call_identity_missing")
        if isinstance(self._client, BoundReferenceClient):
            self._client.bind_call(
                CallIdentity(
                    run_id=capture.run_id,
                    session_id=capture.session_id,
                    step_id=capture.step_id,
                    call_id=invocation.actor.call_id,
                )
            )
        decision, behavior = self._decision(request, script)
        capture.decisions.append(
            DecisionFact(
                run_id=capture.run_id,
                session_id=capture.session_id,
                step_id=capture.step_id,
                call_id=invocation.actor.call_id,
                implementation=key,
                allowed_action_ids=tuple(allowed),
                selected_action_ids=decision.selected_action_ids,
                behavior=behavior,
                schema_valid=behavior != "schema_rejection",
            )
        )
        actions = tuple(
            allowed[a] for a in decision.selected_action_ids if self._available(allowed[a])
        )
        filtered = FixtureScript(decision.output_text.encode(), actions, decision.output_mime_type)
        result = ScriptedBackend({key: filtered}).invoke(invocation)
        executed_ids = {a.action_id for a in actions}
        return replace(
            result,
            skipped_action_ids=(
                *result.skipped_action_ids,
                *(a for a in allowed if a not in executed_ids),
            ),
        )

    def _decision(
        self, request: ReferenceModelRequest, script: FixtureScript
    ) -> tuple[ReferenceModelDecision, ModelBehavior]:
        try:
            decision = _checked_decision(self._client.decide(request), request, script)
        except (ModelOutcomeError, ValidationError) as error:
            behavior = (
                error.behavior if isinstance(error, ModelOutcomeError) else "schema_rejection"
            )
            return ReferenceModelDecision(
                selected_action_ids=(), output_text="", output_mime_type=script.output_mime_type
            ), behavior
        return (
            decision,
            "no_call"
            if request.allowed_action_ids and not decision.selected_action_ids
            else "normal",
        )

    def _available(self, action: ToolScriptAction) -> bool:
        arguments = action.arguments
        if (
            not isinstance(arguments, ReadMemoryArgs)
            or self._store.get_memory_head(self._capture.run_id, arguments.key) is not None
        ):
            return True
        self._capture.issues.append(
            ExecutionIssue(
                run_id=self._capture.run_id,
                session_id=self._capture.session_id,
                step_id=self._capture.step_id,
                reason="memory_not_present",
                references=(action.action_id,),
            )
        )
        return False


def _checked_decision(
    decision: ReferenceModelDecision, request: ReferenceModelRequest, script: FixtureScript
) -> ReferenceModelDecision:
    decision = ReferenceModelDecision.model_validate(decision.model_dump())
    selected = decision.selected_action_ids
    if (
        len(set(selected)) != len(selected)
        or not set(selected) <= set(request.allowed_action_ids)
        or decision.output_mime_type != script.output_mime_type
    ):
        raise ModelOutcomeError("schema_rejection")
    return decision
