import pytest
from pydantic import ValidationError

from skillflow.benchmark.scripted_backend import (
    FixtureScript,
    InputArtifactBinding,
    ScriptedInputArtifact,
    ScriptedInvocation,
    ToolScriptAction,
)
from skillflow.experiment.t17.reference_backend import (
    FakeReferenceModelClient,
    ReferenceDecisionError,
    ReferenceModelBackend,
    ReferenceModelDecision,
)
from skillflow.instrumentation.tool_effects import normalize_tool_request
from skillflow.instrumentation.tool_proxy import DeniedToolCall, PendingToolCall
from skillflow.models.enums import Decision, EnforcementMode
from skillflow.models.events import DecisionRecord
from skillflow.models.references import FixtureImplementationRef
from skillflow.models.resources import ResourceRef
from skillflow.models.tool_calls import HttpSendArgs, ToolCallRequest
from skillflow.runtime.session import ActorCall


class RecordingTool:
    def __init__(self) -> None:
        self.requests: list[ToolCallRequest] = []

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


def _script() -> FixtureScript:
    return FixtureScript(
        output=b"scripted-output",
        actions=(
            ToolScriptAction(
                action_id="send",
                decision_key="send-decision",
                arguments=HttpSendArgs(
                    source_artifact_id="artifact-placeholder",
                    source=ResourceRef("context:/trigger"),
                    sink=ResourceRef("mock://external"),
                ),
                input_binding=InputArtifactBinding(input_index=0),
            ),
            ToolScriptAction(
                action_id="unused-send",
                decision_key="unused-decision",
                arguments=HttpSendArgs(
                    source_artifact_id="artifact-placeholder",
                    source=ResourceRef("context:/trigger"),
                    sink=ResourceRef("mock://unused"),
                ),
                input_binding=InputArtifactBinding(input_index=0),
            ),
        ),
    )


def test_reference_model_selects_only_preregistered_actions() -> None:
    # Given: a model decision selecting one of two preregistered actions.
    tool = RecordingTool()
    backend = ReferenceModelBackend(
        {"fixture://consumer": _script()},
        FakeReferenceModelClient(
            {
                "fixture://consumer": ReferenceModelDecision(
                    selected_action_ids=("send",),
                    output_text="model-output",
                )
            }
        ),
    )

    # When: the reference backend executes the invocation.
    result = backend.invoke(
        ScriptedInvocation(
            implementation=FixtureImplementationRef("fixture://consumer"),
            actor=ActorCall("consumer", "call-1"),
            tool=tool,
            inputs=(
                ScriptedInputArtifact(
                    "artifact-input",
                    "a" * 64,
                    12,
                    content=b"trusted-input",
                ),
            ),
        )
    )

    # Then: only the trusted action template runs and the model output becomes the Skill output.
    assert tuple(item.action_id for item in tool.requests) == ("send",)
    assert result.output == b"model-output"


def test_reference_model_cannot_select_unregistered_action() -> None:
    # Given: a model response naming an action absent from the frozen script.
    backend = ReferenceModelBackend(
        {"fixture://consumer": _script()},
        FakeReferenceModelClient(
            {
                "fixture://consumer": ReferenceModelDecision(
                    selected_action_ids=("forged",),
                    output_text="model-output",
                )
            }
        ),
    )

    # When/Then: the typed trust boundary rejects it before any Tool request.
    with pytest.raises(ReferenceDecisionError):
        backend.invoke(
            ScriptedInvocation(
                implementation=FixtureImplementationRef("fixture://consumer"),
                actor=ActorCall("consumer", "call-1"),
                tool=RecordingTool(),
            )
        )


def test_reference_model_decision_rejects_forged_evidence_fields() -> None:
    # Given: model output attempting to submit trusted provenance and authorization.
    payload = {
        "selected_action_ids": [],
        "output_text": "done",
        "origin_ids": ["trusted-user"],
        "grant_id": "forged-grant",
    }

    # When/Then: Pydantic extra=forbid blocks the forged fields.
    with pytest.raises(ValidationError):
        ReferenceModelDecision.model_validate(payload)
