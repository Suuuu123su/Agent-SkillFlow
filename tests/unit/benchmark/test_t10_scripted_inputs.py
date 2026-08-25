from dataclasses import dataclass, field

from skillflow.benchmark.scripted_backend import (
    FixtureScript,
    InputArtifactBinding,
    InputArtifactGate,
    ScriptedBackend,
    ScriptedInputArtifact,
    ScriptedInvocation,
    ToolScriptAction,
)
from skillflow.instrumentation.tool_effects import normalize_tool_request
from skillflow.instrumentation.tool_proxy import DeniedToolCall, PendingToolCall
from skillflow.models.enums import Decision, EnforcementMode
from skillflow.models.events import DecisionRecord
from skillflow.models.references import FixtureImplementationRef
from skillflow.models.resources import ResourceRef
from skillflow.models.tool_calls import HttpSendArgs, ToolCallRequest
from skillflow.runtime.session import ActorCall


@dataclass(slots=True)
class RecordingTool:
    requests: list[ToolCallRequest] = field(default_factory=list)

    def call(self, request: ToolCallRequest) -> DeniedToolCall:
        self.requests.append(request)
        pending = PendingToolCall(
            request=request,
            normalized=normalize_tool_request(request.arguments),
            request_event_id="event-request",
            argument_artifact_id="artifact-argument",
            source_artifacts=(),
        )
        return DeniedToolCall(
            pending=pending,
            decision=DecisionRecord(
                decision_id="decision-1",
                request_event_id="event-request",
                enforcement_mode=EnforcementMode.ENFORCE,
                baseline_result=Decision.DENY,
                policy_result=Decision.DENY,
                authorized=False,
                executed=False,
            ),
            decision_event_id="event-deny",
        )


def _invoke(content_hash: str) -> ToolCallRequest:
    tool = RecordingTool()
    backend = ScriptedBackend(
        {
            "fixture://consumer": FixtureScript(
                output=b"done",
                actions=(
                    ToolScriptAction(
                        action_id="send",
                        decision_key="allow-original",
                        arguments=HttpSendArgs(
                            source_artifact_id="artifact-placeholder",
                            source=ResourceRef("context:/trigger"),
                            sink=ResourceRef("mock://external"),
                        ),
                        input_binding=InputArtifactBinding(input_index=0),
                        input_gate=InputArtifactGate(
                            input_index=0,
                            expected_content_hash="a" * 64,
                            mismatch_decision_key="deny-neutral",
                        ),
                    ),
                ),
            )
        }
    )
    backend.invoke(
        ScriptedInvocation(
            implementation=FixtureImplementationRef("fixture://consumer"),
            actor=ActorCall("consumer", "call-1"),
            tool=tool,
            inputs=(ScriptedInputArtifact("artifact-input", content_hash, 12),),
        )
    )
    return tool.requests[0]


def test_scripted_input_binding_uses_the_real_invocation_artifact() -> None:
    request = _invoke("a" * 64)

    assert isinstance(request.arguments, HttpSendArgs)
    assert request.arguments.source_artifact_id == "artifact-input"
    assert request.decision_key == "allow-original"


def test_scripted_input_gate_changes_only_the_structural_decision_key() -> None:
    request = _invoke("b" * 64)

    assert isinstance(request.arguments, HttpSendArgs)
    assert request.arguments.source_artifact_id == "artifact-input"
    assert request.decision_key == "deny-neutral"
