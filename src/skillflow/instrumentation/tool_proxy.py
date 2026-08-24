"""Tool 请求、决策、执行与 Receipt 编排。"""

from dataclasses import dataclass
from typing import TypeAlias, assert_never

from skillflow.instrumentation.decision_stub import DecisionProvider, StubDecisionProvider
from skillflow.instrumentation.errors import DecisionFixtureError
from skillflow.instrumentation.mock_tools import MockExecutionRequest, MockToolAdapter
from skillflow.instrumentation.tool_effects import (
    NormalizedToolRequest,
    normalize_tool_request,
)
from skillflow.instrumentation.tool_receipt import ToolReceipt
from skillflow.instrumentation.tool_types import ToolCallRequest
from skillflow.models.effects import EffectRecord
from skillflow.models.enums import (
    ArtifactType,
    Decision,
    EnforcementMode,
    EventType,
    TrustLevel,
)
from skillflow.models.events import DecisionRecord
from skillflow.runtime.session import (
    ActorCall,
    ArtifactEmission,
    EventEmission,
    RuntimeRecorder,
)

__all__ = (
    "AllowedToolCall",
    "DeniedToolCall",
    "ExecutedToolCall",
    "InstrumentedTool",
    "StubDecisionProvider",
    "ToolCallRequest",
)


@dataclass(frozen=True, slots=True)
class PendingToolCall:
    """已经记录 TOOL_CALL_REQUEST、尚未决策的请求。"""

    request: ToolCallRequest
    normalized: NormalizedToolRequest
    request_event_id: str
    argument_artifact_id: str


@dataclass(frozen=True, slots=True)
class AllowedToolCall:
    """Stub fixture 明确允许的待执行 Tool 请求。"""

    pending: PendingToolCall
    decision_id: str
    decision_event_id: str


@dataclass(frozen=True, slots=True)
class DeniedToolCall:
    """Stub fixture 明确拒绝的 Tool 请求。"""

    pending: PendingToolCall
    decision: DecisionRecord
    decision_event_id: str


@dataclass(frozen=True, slots=True)
class ExecutedToolCall:
    """Mock Tool 已执行并签发 Receipt 的结果。"""

    pending: PendingToolCall
    receipt: ToolReceipt
    receipt_artifact_id: str
    output_artifact_ids: tuple[str, ...]


ToolCallOutcome: TypeAlias = DeniedToolCall | ExecutedToolCall


class InstrumentedTool:
    """分阶段记录请求、决策、Mock 执行和 Receipt。"""

    def __init__(
        self,
        recorder: RuntimeRecorder,
        decisions: DecisionProvider,
        adapter: MockToolAdapter,
    ) -> None:
        """绑定记录器、临时决策 seam 与唯一 Mock Tool Adapter。"""
        self._recorder = recorder
        self._decisions = decisions
        self._adapter = adapter

    def request(self, request: ToolCallRequest) -> PendingToolCall:
        """规范化 Effect 并记录参数 Artifact 与 TOOL_CALL_REQUEST。"""
        normalized = normalize_tool_request(request.arguments)
        source_labels = tuple(
            self._recorder.require_artifact(artifact_id).observed_label
            for artifact_id in normalized.source_artifact_ids
        )
        origins = (
            frozenset(origin for label in source_labels for origin in label.origins)
            if source_labels
            else frozenset({request.actor_id})
        )
        argument = self._recorder.record_artifact(
            ArtifactEmission(
                event_type=EventType.TOOL_CALL_REQUEST,
                artifact_type=ArtifactType.TOOL_ARG,
                content=request.arguments.model_dump_json().encode(),
                actor=ActorCall(request.actor_id, request.call_id),
                input_artifact_ids=normalized.source_artifact_ids,
                origins=origins,
                trust=TrustLevel.UNTRUSTED,
                mime_type="application/json",
                requested_effect=normalized.effect,
                metadata={"tool": request.arguments.kind.value},
            )
        )
        return PendingToolCall(
            request=request,
            normalized=normalized,
            request_event_id=argument.created_by_event_id,
            argument_artifact_id=argument.artifact_id,
        )

    def decision(self, pending: PendingToolCall) -> AllowedToolCall | DeniedToolCall:
        """记录 Stub allow/deny，且不复制 T08 授权逻辑。"""
        result = self._decisions.decide(pending.request.decision_key)
        decision_id = self._recorder.new_id("decision")
        actor = ActorCall("harness", pending.request.call_id)
        match result:
            case Decision.ALLOW:
                event = self._recorder.record_event(
                    EventEmission(
                        event_type=EventType.TOOL_CALL_ALLOW,
                        actor=actor,
                        input_artifact_ids=(pending.argument_artifact_id,),
                        requested_effect=pending.normalized.effect,
                        metadata={"tool": pending.request.arguments.kind.value},
                    )
                )
                return AllowedToolCall(pending, decision_id, event.event_id)
            case Decision.DENY:
                decision = self._decision_record(pending, decision_id, result)
                event = self._recorder.record_event(
                    EventEmission(
                        event_type=EventType.TOOL_CALL_DENY,
                        actor=actor,
                        input_artifact_ids=(pending.argument_artifact_id,),
                        requested_effect=pending.normalized.effect,
                        decision_id=decision_id,
                        decision=decision,
                        metadata={"tool": pending.request.arguments.kind.value},
                    )
                )
                return DeniedToolCall(pending, decision, event.event_id)
            case Decision.CONFIRM:
                raise DecisionFixtureError(pending.request.decision_key, "T05 Stub 禁止 confirm")
            case _ as unreachable:
                assert_never(unreachable)

    def execute(self, allowed: AllowedToolCall) -> ExecutedToolCall:
        """仅执行 Allowed 状态，并原子记录 Decision、Effect 和 Receipt Artifact。"""
        fact_ids = self._recorder.allocate_artifact_ids()
        effect_id = self._recorder.new_id("effect")
        receipt_id = self._recorder.new_id("receipt")
        executed = self._adapter.execute(
            MockExecutionRequest(
                arguments=allowed.pending.request.arguments,
                actor=ActorCall(
                    allowed.pending.request.actor_id,
                    allowed.pending.request.call_id,
                ),
                effect_id=effect_id,
                request_event_id=allowed.pending.request_event_id,
                result_event_id=fact_ids.event_id,
                decision_id=allowed.decision_id,
                receipt_id=receipt_id,
                timestamp=self._recorder.now(),
            )
        )
        decision = self._decision_record(
            allowed.pending,
            allowed.decision_id,
            Decision.ALLOW,
        )
        effect = EffectRecord(
            effect_id=effect_id,
            effect=allowed.pending.normalized.effect,
            request_event_id=allowed.pending.request_event_id,
            decision_id=allowed.decision_id,
            result_event_id=fact_ids.event_id,
            tool_receipt_id=receipt_id,
            executed=True,
        )
        receipt_artifact = self._recorder.record_prepared_artifact(
            fact_ids,
            ArtifactEmission(
                event_type=EventType.TOOL_CALL_RESULT,
                artifact_type=ArtifactType.TOOL_RETURN,
                content=executed.receipt.to_bytes(),
                actor=ActorCall(
                    f"tool:{allowed.pending.request.arguments.kind.value}",
                    allowed.pending.request.call_id,
                ),
                input_artifact_ids=(
                    allowed.pending.argument_artifact_id,
                    *executed.output_artifact_ids,
                ),
                origins=frozenset({allowed.pending.request.actor_id}),
                trust=TrustLevel.TRUSTED,
                mime_type="application/json",
                requested_effect=allowed.pending.normalized.effect,
                decision_id=allowed.decision_id,
                decision=decision,
                effect=effect,
                metadata={"tool": allowed.pending.request.arguments.kind.value},
            ),
        )
        return ExecutedToolCall(
            pending=allowed.pending,
            receipt=executed.receipt,
            receipt_artifact_id=receipt_artifact.artifact_id,
            output_artifact_ids=executed.output_artifact_ids,
        )

    def call(self, request: ToolCallRequest) -> ToolCallOutcome:
        """通过类型化阶段执行一次 Tool 调用。"""
        decided = self.decision(self.request(request))
        match decided:
            case AllowedToolCall():
                return self.execute(decided)
            case DeniedToolCall():
                return decided
            case _ as unreachable:
                assert_never(unreachable)

    @staticmethod
    def _decision_record(
        pending: PendingToolCall,
        decision_id: str,
        result: Decision,
    ) -> DecisionRecord:
        return DecisionRecord(
            decision_id=decision_id,
            request_event_id=pending.request_event_id,
            enforcement_mode=EnforcementMode.MONITOR,
            baseline_result=result,
            policy_result=result,
            authorized=False,
            executed=result is Decision.ALLOW,
            reason_codes=("t05_stub_fixture",),
        )
