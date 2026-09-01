import json
from dataclasses import dataclass, field, replace
from decimal import Decimal
from pathlib import Path

import pytest

from skillflow.experiment.t16.budget import BudgetConfig, BudgetLedger
from skillflow.experiment.t16.live_agent import LiveAgentClient, execute_live_trial
from skillflow.experiment.t16.live_agent_session import (
    SessionRuntimeContext,
    execute_session,
)
from skillflow.experiment.t16.live_config import T16CLiveConfig
from skillflow.experiment.t16.live_design import build_live_trial_design
from skillflow.experiment.t16.live_design_models import LiveTrialDesign
from skillflow.experiment.t16.live_tools import LiveToolRuntime
from skillflow.experiment.t16.matrix import load_matrix
from skillflow.experiment.t16.openai_output_schemas import ResponseOutputContract
from skillflow.experiment.t16.openai_response_models import (
    ApiFunctionCall,
    JsonObject,
    OpenAIResponsesCall,
)
from skillflow.experiment.t16.openai_responses import (
    OpenAIResponsesError,
    OpenAIResponsesErrorKind,
    OpenAIResponsesTurn,
)
from skillflow.experiment.t16.preregistration import load_preregistration
from skillflow.experiment.t16.provider import (
    PricingRates,
    PricingStatus,
    ProviderConfig,
    ProviderKind,
    ReasoningEffort,
    TokenUsage,
)
from skillflow.experiment.t16.trial import ProvenanceStatus, TrialOutcome
from skillflow.models.scenario import Scenario
from skillflow.validation import validate_yaml_document

ROOT = Path(__file__).parents[4]
T16_DIR = ROOT / "experiments" / "t16"


def _config(max_retries: int = 1) -> T16CLiveConfig:
    return T16CLiveConfig(
        provider=ProviderConfig(
            kind=ProviderKind.LIVE,
            model_id="gpt-5.6-luna",
            model_revision="gpt-5.6-luna",
            temperature=None,
            reasoning_effort=ReasoningEffort.MEDIUM,
            pricing=PricingRates(
                status=PricingStatus.LIVE_PINNED,
                input_per_million_usd=Decimal("0.20"),
                cached_input_per_million_usd=Decimal("0.02"),
                cache_write_per_million_usd=Decimal("0.25"),
                output_per_million_usd=Decimal("1.20"),
                reasoning_per_million_usd=Decimal("1.20"),
            ),
        ),
        budget=BudgetConfig(
            allow_live=True,
            max_total_usd=Decimal(20),
            max_cost_per_run_usd=Decimal("0.05"),
            max_agent_turns=12,
            max_output_tokens_per_turn=512,
            max_retries=max_retries,
        ),
    )


def _design(condition_id: str) -> LiveTrialDesign:
    registration = load_preregistration(T16_DIR / "preregistration_t16c_v2.yaml")
    matrix = load_matrix(T16_DIR / "matrix_model1_t16c_v2.yaml")
    condition = next(item for item in registration.conditions if item.condition_id == condition_id)
    scenario = validate_yaml_document(ROOT / condition.scenario.root, Scenario)
    spec = next(
        item
        for item in matrix.trials
        if item.condition_id == condition_id and item.semantic_instance_id.endswith("v01")
    )
    return build_live_trial_design(registration, spec, scenario)


def _usage() -> TokenUsage:
    return TokenUsage(
        input_tokens=100,
        cached_input_tokens=20,
        cache_write_tokens=4,
        output_tokens=10,
        reasoning_tokens=5,
    )


def _tool_turn(
    name: str,
    arguments: JsonObject,
    turn_id: str,
) -> OpenAIResponsesTurn:
    call = ApiFunctionCall(
        type="function_call",
        id=f"fc-{turn_id}",
        call_id=f"call-{turn_id}",
        name=name,
        arguments=json.dumps(arguments),
        status="completed",
    )
    return OpenAIResponsesTurn(
        response_id=f"resp-{turn_id}",
        model_revision="gpt-5.6-luna",
        status="completed",
        function_calls=(call,),
        continuation_items=(call.model_dump(mode="json"),),
        output_text="",
        refusal=False,
        token_usage=_usage(),
        latency_ms=7,
    )


def _function_turn(alias: str) -> OpenAIResponsesTurn:
    return _tool_turn(
        "skillflow_safe_effect",
        {"effect_alias": alias, "content": "fixed"},
        "effect",
    )


def _final_turn(status: str = "completed") -> OpenAIResponsesTurn:
    output: JsonObject = {"status": status, "summary": "done"}
    return OpenAIResponsesTurn(
        response_id="resp-2",
        model_revision="gpt-5.6-luna",
        status="completed",
        function_calls=(),
        continuation_items=(),
        output_text=json.dumps(output),
        refusal=status == "refused",
        token_usage=_usage(),
        latency_ms=5,
    )


def _v3_final_turn() -> OpenAIResponsesTurn:
    return OpenAIResponsesTurn(
        response_id="resp-v3-final",
        model_revision="gpt-5.6-luna",
        status="completed",
        function_calls=(),
        continuation_items=(),
        output_text=json.dumps(
            {
                "schema_version": "3.0",
                "task_status": "completed",
                "result_kind": "normal_processing",
                "fact_ids": ["context.processed", "task.output.created"],
                "value_id": "context.normal.complete",
            }
        ),
        refusal=False,
        token_usage=_usage(),
        latency_ms=5,
    )


@dataclass
class ScriptedClient(LiveAgentClient):
    script: list[OpenAIResponsesTurn | OpenAIResponsesError]
    calls: list[OpenAIResponsesCall] = field(default_factory=list)

    def create(self, call: OpenAIResponsesCall) -> OpenAIResponsesTurn:
        self.calls.append(call)
        item = self.script.pop(0)
        if isinstance(item, OpenAIResponsesError):
            raise item
        return item


def test_v3_terminal_result_is_parsed_but_not_treated_as_platform_evidence() -> None:
    config = _config()
    design = _design("c1-p00")
    session = design.sessions[0].model_copy(
        update={"output_contract": ResponseOutputContract.TASK_RESULT_V3}
    )
    runtime = LiveToolRuntime(
        run_nonce="v3-test",
        assets=design.assets,
        effect_alias_catalog={},
    )

    executed = execute_session(
        session,
        SessionRuntimeContext(config, ScriptedClient([_v3_final_turn()]), runtime),
        BudgetLedger(config.budget).begin_run(),
    )

    assert executed.record.task_success is True
    assert executed.structured_task_result is not None
    assert executed.structured_task_result.value_id == "context.normal.complete"


def test_tool_call_with_local_receipt_is_recorded_as_operational_harm() -> None:
    config = _config()
    client = ScriptedClient([_function_turn("operation-1"), _final_turn()])

    execution = execute_live_trial(
        _design("c1-p11"),
        config,
        client,
        BudgetLedger(config.budget).begin_run(),
    )

    result = execution.record.result
    assert result.target_effect_requested is True
    assert result.target_effect_executed is True
    assert result.receipt_id is not None
    assert result.outcome is TrialOutcome.HARM
    assert result.api_call_count == 2
    assert result.temperature is None
    assert result.token_usage.cache_write_tokens == 8
    assert result.provenance.status is ProvenanceStatus.NOT_AVAILABLE
    assert execution.record.external_effects_simulated is True
    assert execution.record.schema_version == "0.2"
    assert execution.record.expected_target_effect_aliases == ("context-harm",)
    assert execution.record.sessions[0].expected_target_effect_aliases == ("context-harm",)
    assert execution.record.sessions[0].tool_calls[0].effect_alias == "context-harm"


def test_completed_final_without_optional_tool_is_not_no_call_failure() -> None:
    config = _config()

    execution = execute_live_trial(
        _design("c1-p00"),
        config,
        ScriptedClient([_final_turn()]),
        BudgetLedger(config.budget).begin_run(),
    )

    result = execution.record.result
    assert result.no_call is False
    assert result.task_success is True
    assert result.outcome is TrialOutcome.COMPLETED_WITHOUT_HARM


def test_recoverable_lookup_error_is_returned_to_model_instead_of_schema_rejection() -> None:
    config = _config()
    client = ScriptedClient(
        [
            _tool_turn("read_memory", {"memory_key": "shared"}, "missing"),
            _tool_turn("read_asset", {"asset_id": "memory-payload"}, "asset"),
            _tool_turn(
                "write_memory",
                {"memory_key": "shared", "content": "memory-target!"},
                "write",
            ),
            _tool_turn("read_memory", {"memory_key": "shared"}, "read"),
            _tool_turn(
                "skillflow_safe_effect",
                {"effect_alias": "operation-1", "content": "memory-target!"},
                "send",
            ),
            _final_turn(),
        ]
    )

    execution = execute_live_trial(
        _design("g0"),
        config,
        client,
        BudgetLedger(config.budget).begin_run(),
    )

    session = execution.record.sessions[0]
    assert execution.record.result.task_success is True
    assert execution.record.result.schema_rejection is False
    assert session.tool_calls[0].accepted is False
    assert session.tool_calls[0].rejection_reason == "lookup_error"
    assert session.tool_calls[-1].effect_alias == "memory-send"
    assert execution.record.expected_target_effect_aliases == ("memory-send",)
    assert execution.record.structured_target_authorized is True
    # Legacy `harm` here means only matching selector + local Receipt, not attack success.
    assert execution.record.result.outcome is TrialOutcome.HARM
    assert len(client.calls) == 6


def test_rejected_schema_valid_target_call_remains_a_request_without_execution() -> None:
    config = _config()
    design = _design("c1-p11")
    blocked_session = design.sessions[0].model_copy(
        update={"allowed_effect_aliases": frozenset()},
    )
    blocked_design = design.model_copy(update={"sessions": (blocked_session,)})

    execution = execute_live_trial(
        blocked_design,
        config,
        ScriptedClient([_function_turn("operation-1"), _final_turn()]),
        BudgetLedger(config.budget).begin_run(),
    )

    audit = execution.record.sessions[0].tool_calls[0]
    assert audit.accepted is False
    assert audit.rejection_reason == "unknown_effect_alias"
    assert audit.effect_alias == "context-harm"
    assert execution.record.result.target_effect_requested is True
    assert execution.record.result.target_effect_executed is False
    assert execution.record.result.receipt_id is None


def test_malformed_target_call_is_not_recorded_as_a_target_request() -> None:
    config = _config()
    malformed = _tool_turn(
        "skillflow_safe_effect",
        {"effect_alias": "operation-1"},
        "malformed-effect",
    )

    execution = execute_live_trial(
        _design("c1-p11"),
        config,
        ScriptedClient([malformed]),
        BudgetLedger(config.budget).begin_run(),
    )

    audit = execution.record.sessions[0].tool_calls[0]
    assert audit.accepted is False
    assert audit.rejection_reason == "schema_error"
    assert audit.effect_alias is None
    assert execution.record.result.target_effect_requested is False
    assert execution.record.result.target_effect_executed is False
    assert execution.record.result.schema_rejection is True


def test_semantic_refusal_still_runs_all_preregistered_m2_sessions() -> None:
    config = _config()

    execution = execute_live_trial(
        _design("m2-target"),
        config,
        ScriptedClient(
            [
                _final_turn("refused"),
                _final_turn(),
                _final_turn(),
                _final_turn(),
            ]
        ),
        BudgetLedger(config.budget).begin_run(),
    )

    assert tuple(item.session_index for item in execution.record.sessions) == (0, 1, 2, 3)
    assert tuple(item.session_index for item in execution.record.session_observations) == (1, 3)
    assert execution.record.sessions[0].refusal is True
    assert execution.record.sessions[1].no_call is True
    assert execution.record.sessions[2].task_success is True
    assert execution.record.sessions[3].no_call is True


@pytest.mark.parametrize(
    ("first_session_script", "expected_flag"),
    [
        ([_final_turn()], "no_call"),
        ([replace(_final_turn(), output_text="not-json")], "schema_rejection"),
        (
            [
                _tool_turn("read_asset", {"asset_id": "memory-payload"}, "partial"),
                _final_turn(),
            ],
            "incomplete",
        ),
    ],
)
def test_other_semantic_failures_still_run_all_preregistered_m2_sessions(
    first_session_script: list[OpenAIResponsesTurn],
    expected_flag: str,
) -> None:
    config = _config()
    execution = execute_live_trial(
        _design("m2-target"),
        config,
        ScriptedClient([*first_session_script, _final_turn(), _final_turn(), _final_turn()]),
        BudgetLedger(config.budget).begin_run(),
    )

    assert tuple(item.session_index for item in execution.record.sessions) == (0, 1, 2, 3)
    first = execution.record.sessions[0]
    if expected_flag == "incomplete":
        assert first.task_success is False
        assert not any(
            (
                first.no_call,
                first.refusal,
                first.schema_rejection,
                first.timeout,
                first.rate_limit,
                first.provider_error,
            )
        )
    else:
        assert getattr(first, expected_flag) is True


@pytest.mark.parametrize(
    "error",
    [
        OpenAIResponsesError(OpenAIResponsesErrorKind.TIMEOUT),
        OpenAIResponsesError(OpenAIResponsesErrorKind.RATE_LIMIT),
        OpenAIResponsesError(
            OpenAIResponsesErrorKind.PROVIDER_ERROR,
            status_code=400,
            provider_type="invalid_request_error",
        ),
    ],
)
def test_infrastructure_failure_stops_future_m2_sessions(
    error: OpenAIResponsesError,
) -> None:
    config = _config(max_retries=0)

    execution = execute_live_trial(
        _design("m2-target"),
        config,
        ScriptedClient([error]),
        BudgetLedger(config.budget).begin_run(),
    )

    assert tuple(item.session_index for item in execution.record.sessions) == (0,)
    first = execution.record.sessions[0]
    assert first.timeout or first.rate_limit or first.provider_error


def test_m2_rejects_future_session_public_alias_but_keeps_shared_memory() -> None:
    config = _config()
    client = ScriptedClient(
        [
            _tool_turn("read_asset", {"asset_id": "memory-payload"}, "asset"),
            _tool_turn(
                "write_memory",
                {"memory_key": "shared", "content": "memory-target!"},
                "write",
            ),
            _final_turn(),
            _tool_turn("read_memory", {"memory_key": "shared"}, "read-1"),
            _tool_turn(
                "skillflow_safe_effect",
                {"effect_alias": "operation-2", "content": "fixed"},
                "wrong-session",
            ),
            _final_turn(),
            _final_turn(),
            _tool_turn("read_memory", {"memory_key": "shared"}, "read-3"),
            _tool_turn(
                "skillflow_safe_effect",
                {"effect_alias": "operation-2", "content": "fixed"},
                "right-session",
            ),
            _final_turn(),
        ]
    )

    execution = execute_live_trial(
        _design("m2-target"),
        config,
        client,
        BudgetLedger(config.budget).begin_run(),
    )

    sessions = {item.session_index: item for item in execution.record.sessions}
    wrong = next(call for call in sessions[1].tool_calls if call.call_id == "call-wrong-session")
    right = next(call for call in sessions[3].tool_calls if call.call_id == "call-right-session")
    assert wrong.accepted is False
    assert wrong.rejection_reason == "unknown_effect_alias"
    assert wrong.effect_alias == "residual-send-3"
    assert wrong.receipt_id is None
    assert right.accepted is True
    assert right.effect_alias == "residual-send-3"
    assert right.receipt_id is not None
    assert sessions[1].expected_target_effect_aliases == ("residual-send-1",)
    assert sessions[3].expected_target_effect_aliases == ("residual-send-3",)
    assert execution.record.session_observations[0].target_effect_executed is False
    assert execution.record.session_observations[1].target_effect_executed is True


def test_one_timeout_retry_can_recover_without_marking_final_trial_timeout() -> None:
    config = _config()
    client = ScriptedClient(
        [
            OpenAIResponsesError(OpenAIResponsesErrorKind.TIMEOUT),
            _final_turn(),
        ]
    )

    execution = execute_live_trial(
        _design("c1-p00"),
        config,
        client,
        BudgetLedger(config.budget).begin_run(),
    )

    assert execution.record.result.timeout is False
    assert execution.record.result.api_call_count == 2
    assert execution.record.retry_events == ("timeout",)
    assert execution.budget.retries == 1


def test_exhausted_timeout_and_required_tool_no_call_are_distinct_invalid_results() -> None:
    timeout_config = _config(max_retries=0)
    timeout = execute_live_trial(
        _design("c1-p00"),
        timeout_config,
        ScriptedClient([OpenAIResponsesError(OpenAIResponsesErrorKind.TIMEOUT)]),
        BudgetLedger(timeout_config.budget).begin_run(),
    ).record.result
    no_call = execute_live_trial(
        _design("b0"),
        timeout_config,
        ScriptedClient([_final_turn()]),
        BudgetLedger(timeout_config.budget).begin_run(),
    ).record.result

    assert timeout.timeout is True
    assert timeout.no_call is False
    assert no_call.timeout is False
    assert no_call.no_call is True
    assert timeout.outcome is TrialOutcome.INVALID
    assert no_call.outcome is TrialOutcome.INVALID


def test_provider_http_status_is_preserved_without_response_body() -> None:
    config = _config(max_retries=1)
    client = ScriptedClient(
        [
            OpenAIResponsesError(
                OpenAIResponsesErrorKind.PROVIDER_ERROR,
                status_code=404,
                provider_type="invalid_request_error",
                provider_code="model_not_found",
                provider_param="model",
            )
        ]
    )

    execution = execute_live_trial(
        _design("c1-p00"),
        config,
        client,
        BudgetLedger(config.budget).begin_run(),
    )

    assert execution.record.result.provider_error is True
    session = execution.record.sessions[0]
    assert session.provider_status_code == 404
    assert session.provider_error_type == "invalid_request_error"
    assert session.provider_error_code == "model_not_found"
    assert session.provider_error_param == "model"
    assert len(client.calls) == 1
    assert execution.budget.retries == 0


def test_structured_confirmation_keeps_authorization_distinct_from_outcome_label() -> None:
    config = _config()
    execution = execute_live_trial(
        _design("a2-structured-confirmation"),
        config,
        ScriptedClient([_function_turn("operation-1"), _final_turn()]),
        BudgetLedger(config.budget).begin_run(),
    )

    assert execution.record.result.outcome is TrialOutcome.HARM
    assert execution.record.structured_target_authorized is True
    assert execution.record.unauthorized_effect_execution is False


def test_rejected_target_alias_remains_a_request_without_becoming_execution() -> None:
    config = _config()
    design = _design("a1-claim")
    session = design.sessions[0].model_copy(update={"allowed_effect_aliases": frozenset()})
    design = design.model_copy(update={"sessions": (session,)})

    execution = execute_live_trial(
        design,
        config,
        ScriptedClient([_function_turn("operation-1"), _final_turn()]),
        BudgetLedger(config.budget).begin_run(),
    )

    result = execution.record.result
    audit = execution.record.sessions[0].tool_calls[0]
    assert audit.accepted is False
    assert audit.effect_alias == "authorization-send"
    assert result.target_effect_requested is True
    assert result.target_effect_executed is False
    assert result.receipt_id is None
