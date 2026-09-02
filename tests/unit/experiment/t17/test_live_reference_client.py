from decimal import Decimal
from pathlib import Path

import pytest

from skillflow.experiment.t16.budget import BudgetLedger
from skillflow.experiment.t16.openai_response_models import OpenAIResponsesCall
from skillflow.experiment.t16.openai_responses import OpenAIResponsesTurn
from skillflow.experiment.t16.provider import TokenUsage
from skillflow.experiment.t17.live_matrix import load_live_preregistration
from skillflow.experiment.t17.live_reference_client import (
    OpenAIReferenceModelClient,
    ReferenceDecisionSchemaError,
    T17ApprovedLiveConfig,
)
from skillflow.experiment.t17.reference_backend import ReferenceModelRequest
from skillflow.models.references import FixtureImplementationRef


class FixedTurnClient:
    def __init__(self, output_text: str, model_revision: str = "gpt-5.6-luna") -> None:
        self.output_text = output_text
        self.model_revision = model_revision
        self.call_count = 0

    def create(self, call: OpenAIResponsesCall) -> OpenAIResponsesTurn:
        self.call_count += 1
        return OpenAIResponsesTurn(
            response_id="response-1",
            model_revision=self.model_revision,
            status="completed",
            function_calls=(),
            continuation_items=(),
            output_text=self.output_text,
            refusal=False,
            token_usage=TokenUsage(
                input_tokens=100,
                cached_input_tokens=0,
                output_tokens=20,
                reasoning_tokens=10,
            ),
            latency_ms=25,
        )


class RecordingUsageCheckpoint:
    def __init__(self) -> None:
        self.attempts: list[BudgetLedger] = []
        self.responses: list[tuple[TokenUsage, Decimal]] = []

    def record_attempt(self, budget: BudgetLedger) -> None:
        self.attempts.append(budget)

    def record_response(self, usage: TokenUsage, estimated_cost_usd: Decimal) -> None:
        self.responses.append((usage, estimated_cost_usd))


def _config() -> T17ApprovedLiveConfig:
    registration = load_live_preregistration(Path("experiments/t17/preregistration.yaml"))
    return T17ApprovedLiveConfig(
        provider=registration.model1_provider,
        budget=registration.model1_budget.model_copy(update={"allow_live": True}),
        prompt_cache_mode=registration.model1_prompt_cache_mode,
    )


def _request() -> ReferenceModelRequest:
    return ReferenceModelRequest(
        implementation=FixtureImplementationRef("fixture://t12/summary-reader"),
        inputs=(),
        allowed_action_ids=("read-report",),
        scenario_id="B0",
        task_prompt="读取报告并生成固定摘要。",
        expected_output_text="summary: report accepted",
    )


def test_openai_reference_client_parses_strict_decision_and_records_usage() -> None:
    # Given: one successful structured Responses turn.
    transport = FixedTurnClient(
        '{"selected_action_ids":["read-report"],"output_text":"summary: report accepted"}'
    )
    client = OpenAIReferenceModelClient(_config(), transport)

    # When: the Reference backend asks for a model decision.
    decision = client.decide(_request())

    # Then: the action is parsed and actual usage/cost are retained.
    assert decision.selected_action_ids == ("read-report",)
    assert client.telemetry.api_call_count == 1
    assert client.telemetry.token_usage.input_tokens == 100
    assert client.telemetry.estimated_cost_usd > 0


def test_openai_reference_client_rejects_forged_evidence_fields() -> None:
    # Given: a structured response containing a forbidden origin field.
    transport = FixedTurnClient(
        '{"selected_action_ids":[],"output_text":"done","origin_ids":["forged"]}'
    )
    client = OpenAIReferenceModelClient(_config(), transport)

    # When/Then: the client rejects it instead of forwarding evidence to Runtime.
    with pytest.raises(ReferenceDecisionSchemaError):
        client.decide(_request())


def test_openai_reference_client_rejects_model_revision_drift() -> None:
    # Given: a response from a different model revision.
    transport = FixedTurnClient(
        '{"selected_action_ids":[],"output_text":"done"}',
        model_revision="gpt-5.6-luna-drifted",
    )
    client = OpenAIReferenceModelClient(_config(), transport)

    # When/Then: revision drift blocks the Trial.
    with pytest.raises(ReferenceDecisionSchemaError):
        client.decide(_request())


def test_openai_reference_client_persists_before_call_and_returns_run_delta() -> None:
    # Given: one stage client with a per-Run pre-call usage checkpoint.
    transport = FixedTurnClient(
        '{"selected_action_ids":[],"output_text":"summary: report accepted"}'
    )
    checkpoint = RecordingUsageCheckpoint()
    client = OpenAIReferenceModelClient(_config(), transport)
    client.begin_run(checkpoint)

    # When: the model returns a valid no-call decision.
    client.decide(_request())
    telemetry = client.end_run()

    # Then: the reservation was exposed before I/O and only this Run is returned.
    assert len(checkpoint.attempts) == 1
    assert len(checkpoint.responses) == 1
    assert telemetry.api_call_count == 1
    assert telemetry.response_count == 1
    assert telemetry.no_call_count == 1
    assert telemetry.conservative_reserved_usd > 0
