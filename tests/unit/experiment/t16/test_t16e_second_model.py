import json
import socket
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from skillflow.experiment.t16 import (
    live_agent_calls,
    live_config,
    task_success_canary_cli,
    task_success_canary_preflight,
    task_success_canary_run,
    task_success_live_config,
)
from skillflow.experiment.t16.budget import BudgetConfig, BudgetLedger, CallReservation
from skillflow.experiment.t16.live_agent_calls import invoke_with_retry
from skillflow.experiment.t16.live_canary_usage import load_canary_usage_events
from skillflow.experiment.t16.live_usage_store import (
    ActualUsageStatus,
    LiveTrialTerminalStatus,
)
from skillflow.experiment.t16.openai_response_models import (
    ApiFunctionCall,
    OpenAIResponsesCall,
)
from skillflow.experiment.t16.openai_responses import (
    OpenAIResponsesError,
    OpenAIResponsesErrorKind,
    OpenAIResponsesTurn,
)
from skillflow.experiment.t16.provider import ReasoningEffort, TokenUsage
from skillflow.experiment.t16.task_success_canary_run import T16D2CanaryRunRequest
from skillflow.experiment.t16.task_success_live_mock import TaskSuccessMockLiveClient
from skillflow.experiment.t16.task_success_live_store import load_t16d2_raw_records
from skillflow.schemas import schema_documents

ROOT = Path(__file__).parents[4]
SECOND_MODEL_ID = "gpt-5.5-2026-04-23"


@dataclass
class _FixedUsageClient:
    calls: int = 0

    def create(self, call: OpenAIResponsesCall) -> OpenAIResponsesTurn:
        self.calls += 1
        assert "prompt_cache_options" not in call.payload()
        return OpenAIResponsesTurn(
            response_id="response-1",
            model_revision=call.model,
            status="completed",
            function_calls=(),
            continuation_items=(),
            output_text="",
            refusal=False,
            token_usage=TokenUsage(
                input_tokens=100,
                cached_input_tokens=0,
                output_tokens=10,
                reasoning_tokens=5,
                cache_write_tokens=0,
            ),
            latency_ms=10,
        )


@dataclass
class _ProviderErrorClient:
    calls: int = 0

    def create(self, call: OpenAIResponsesCall) -> OpenAIResponsesTurn:
        del call
        self.calls += 1
        raise OpenAIResponsesError(
            OpenAIResponsesErrorKind.PROVIDER_ERROR,
            status_code=400,
        )


@dataclass
class _InspectingSecondModelClient:
    delegate: TaskSuccessMockLiveClient = field(default_factory=TaskSuccessMockLiveClient)
    calls: int = 0

    def create(self, call: OpenAIResponsesCall) -> OpenAIResponsesTurn:
        self.calls += 1
        assert call.model == SECOND_MODEL_ID
        assert call.reasoning_effort is ReasoningEffort.MEDIUM
        assert call.max_output_tokens == 512
        assert "prompt_cache_options" not in call.payload()
        return self.delegate.create(call)


@dataclass
class _EndlessSecondModelClient:
    calls: int = 0

    def create(self, call: OpenAIResponsesCall) -> OpenAIResponsesTurn:
        self.calls += 1
        function = ApiFunctionCall(
            type="function_call",
            id=f"fc-{self.calls}",
            call_id=f"call-{self.calls}",
            name="read_asset",
            arguments=json.dumps({"asset_id": "report"}),
            status="completed",
        )
        return OpenAIResponsesTurn(
            response_id=f"response-{self.calls}",
            model_revision=call.model,
            status="completed",
            function_calls=(function,),
            continuation_items=(function.model_dump(mode="json"),),
            output_text="",
            refusal=False,
            token_usage=TokenUsage(
                input_tokens=100,
                cached_input_tokens=0,
                output_tokens=8,
                reasoning_tokens=4,
                cache_write_tokens=0,
            ),
            latency_ms=1,
        )


@dataclass
class _DriftingSecondModelClient:
    calls: int = 0

    def create(self, call: OpenAIResponsesCall) -> OpenAIResponsesTurn:
        self.calls += 1
        return OpenAIResponsesTurn(
            response_id="response-drift",
            model_revision="gpt-5.5",
            status="completed",
            function_calls=(),
            continuation_items=(),
            output_text="",
            refusal=True,
            token_usage=TokenUsage(
                input_tokens=100,
                cached_input_tokens=0,
                output_tokens=8,
                reasoning_tokens=4,
                cache_write_tokens=0,
            ),
            latency_ms=1,
        )


def test_t16e_config_freezes_the_user_selected_snapshot_and_budget() -> None:
    build_config = task_success_live_config.build_t16e_canary_config

    config = build_config(ROOT)

    assert config.schema_version == "0.3"
    assert config.id == "t16e-v3.1-canary-gpt-5.5-2026-04-23"
    assert config.provider.model_id == SECOND_MODEL_ID
    assert config.provider.model_revision == SECOND_MODEL_ID
    assert config.provider.temperature is None
    assert config.provider.reasoning_effort is ReasoningEffort.MEDIUM
    assert config.provider.pricing.input_per_million_usd == Decimal(5)
    assert config.provider.pricing.cached_input_per_million_usd == Decimal("0.5")
    assert config.provider.pricing.output_per_million_usd == Decimal(30)
    assert config.provider.pricing.reasoning_per_million_usd == Decimal(30)
    assert config.provider.pricing.cache_write_per_million_usd == Decimal(0)
    assert config.budget.max_total_usd == Decimal(1)
    assert config.budget.max_cost_per_run_usd == Decimal("0.10")
    assert config.budget.max_agent_turns == 16
    assert config.budget.max_output_tokens_per_turn == 512
    assert config.budget.max_retries == 1
    assert config.prompt_cache_mode == "automatic"
    assert config.budget_settlement_mode == "actual_reconciled"
    assert task_success_live_config.T16E_CONFIG_SHA256 == (
        "e97aadc7bf5135f57ac64ad9e05e9726e12087f087618a577974e08febebe9ae"
    )


def test_t16e_environment_requires_the_explicit_second_model_names() -> None:
    load_environment = task_success_canary_preflight.load_t16e_environment

    parsed = load_environment(
        {
            "SKILLFLOW_SECOND_PROVIDER": "openai",
            "SKILLFLOW_SECOND_MODEL_ID": SECOND_MODEL_ID,
            "SKILLFLOW_MAX_USD": "1",
            "SKILLFLOW_LIVE_APPROVED": "1",
        }
    )

    assert parsed.provider == "openai"
    assert parsed.model_id == SECOND_MODEL_ID
    assert parsed.max_total_usd == Decimal(1)
    assert parsed.live_approved is True


@pytest.mark.parametrize(
    "changes",
    [
        {"SKILLFLOW_SECOND_PROVIDER": ""},
        {"SKILLFLOW_SECOND_PROVIDER": "fake"},
        {"SKILLFLOW_SECOND_MODEL_ID": "gpt-5.5"},
        {"SKILLFLOW_SECOND_MODEL_ID": "gpt-5.6-luna"},
        {"SKILLFLOW_MAX_USD": "0.99"},
        {"SKILLFLOW_MAX_USD": "invalid"},
        {"SKILLFLOW_LIVE_APPROVED": "0"},
    ],
)
def test_t16e_environment_fails_closed(changes: dict[str, str]) -> None:
    load_environment = task_success_canary_preflight.load_t16e_environment
    environment = {
        "SKILLFLOW_SECOND_PROVIDER": "openai",
        "SKILLFLOW_SECOND_MODEL_ID": SECOND_MODEL_ID,
        "SKILLFLOW_MAX_USD": "1",
        "SKILLFLOW_LIVE_APPROVED": "1",
    }
    environment.update(changes)

    with pytest.raises(task_success_canary_preflight.T16D2CanaryEnvironmentError):
        load_environment(environment)


def test_budget_settlement_replaces_current_reservation_with_actual_cost() -> None:
    config = BudgetConfig(
        allow_live=True,
        max_total_usd=Decimal(1),
        max_cost_per_run_usd=Decimal("0.5"),
        max_agent_turns=16,
        max_output_tokens_per_turn=512,
        max_retries=1,
    )
    reservation = CallReservation(
        estimated_cost_usd=Decimal("0.08"),
        max_output_tokens=512,
    )
    reserved = BudgetLedger(
        config,
        total_spent_usd=Decimal("0.20"),
        run_spent_usd=Decimal("0.10"),
    ).authorize_call(reservation)

    settled = reserved.settle_call(reservation, Decimal("0.01"))

    assert settled.total_spent_usd == Decimal("0.21")
    assert settled.run_spent_usd == Decimal("0.11")
    assert settled.agent_turns == 1


def test_openai_call_omits_explicit_cache_option_for_gpt55() -> None:
    call = OpenAIResponsesCall(
        model=SECOND_MODEL_ID,
        temperature=None,
        reasoning_effort=ReasoningEffort.MEDIUM,
        max_output_tokens=512,
        input_items=({"role": "user", "content": "fixed"},),
        prompt_cache_mode="automatic",
    )

    assert "prompt_cache_options" not in call.payload()


def test_t16e_successful_response_reconciles_reservation_to_actual_cost() -> None:
    config = task_success_live_config.build_t16e_canary_config(ROOT)
    call = OpenAIResponsesCall(
        model=SECOND_MODEL_ID,
        temperature=None,
        reasoning_effort=ReasoningEffort.MEDIUM,
        max_output_tokens=512,
        input_items=({"role": "user", "content": "fixed"},),
        prompt_cache_mode="automatic",
    )
    client = _FixedUsageClient()

    result = invoke_with_retry(call, config, client, BudgetLedger(config.budget))

    assert result.turn is not None
    assert client.calls == 1
    assert result.budget.total_spent_usd == Decimal("0.000950")
    assert result.budget.run_spent_usd == Decimal("0.000950")


def test_t16e_provider_error_keeps_the_unresolved_reservation() -> None:
    config = task_success_live_config.build_t16e_canary_config(ROOT)
    call = OpenAIResponsesCall(
        model=SECOND_MODEL_ID,
        temperature=None,
        reasoning_effort=ReasoningEffort.MEDIUM,
        max_output_tokens=512,
        input_items=({"role": "user", "content": "fixed"},),
        prompt_cache_mode="automatic",
    )
    client = _ProviderErrorClient()

    result = invoke_with_retry(call, config, client, BudgetLedger(config.budget))

    assert result.turn is None
    assert client.calls == 1
    assert result.budget.total_spent_usd > 0
    assert result.budget.run_spent_usd == result.budget.total_spent_usd


def test_t16e_input_bound_reuses_observed_tokens_for_growing_history() -> None:
    tracker_type = live_agent_calls.InputTokenBoundTracker
    config = task_success_live_config.build_t16e_canary_config(ROOT)
    tracker = tracker_type(config)
    first_payload = "x" * 10_000
    second_payload = first_payload + ("y" * 1_000)

    first_bound = tracker.estimate(first_payload)
    tracker.observe(first_payload, 1_000)
    second_bound = tracker.estimate(second_payload)

    assert first_bound == 10_256
    assert 2_000 <= second_bound < 11_256


def test_base_live_config_still_rejects_an_unregistered_model() -> None:
    config_type = live_config.T16ELiveConfig
    payload = task_success_live_config.build_t16d2r_canary_config(ROOT).model_dump(mode="python")
    payload["provider"]["model_id"] = "unregistered-model"
    payload["provider"]["model_revision"] = "unregistered-model"

    with pytest.raises(ValidationError):
        config_type.model_validate(payload)


def test_t16e_mock_canary_reuses_the_frozen_11_without_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        detail = "unexpected real network"
        raise AssertionError(detail)

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(socket.socket, "connect", fail_network)
    execute = task_success_canary_run.execute_t16e_canary_run
    environment = task_success_canary_preflight.load_t16e_environment(
        {
            "SKILLFLOW_SECOND_PROVIDER": "openai",
            "SKILLFLOW_SECOND_MODEL_ID": SECOND_MODEL_ID,
            "SKILLFLOW_MAX_USD": "1",
            "SKILLFLOW_LIVE_APPROVED": "1",
        }
    )
    output = tmp_path / "model2-attempt"
    client = _InspectingSecondModelClient()

    summary = execute(
        T16D2CanaryRunRequest(ROOT, output, environment),
        client,
    )

    records = load_t16d2_raw_records(output / "raw-trials.jsonl")
    events = load_canary_usage_events(output / "actual-usage-journal.jsonl")
    terminals = tuple(item for item in events if item.event_type == "terminal")
    model1_preflight = json.loads(
        (
            ROOT / "runs" / "t16d2-v31-canary-live-20260830-01" / "attempt-01" / "preflight.json"
        ).read_text(encoding="utf-8")
    )
    model2_preflight = json.loads((output / "preflight.json").read_text(encoding="utf-8"))
    assert summary.status == "PASSED"
    assert summary.observed == 11
    assert summary.unrun == 0
    assert summary.config_id == "t16e-v3.1-canary-gpt-5.5-2026-04-23"
    assert summary.provider_model_revisions == (SECOND_MODEL_ID,)
    assert len(records) == 11
    assert {item.live_trial.result.model_id for item in records} == {SECOND_MODEL_ID}
    assert len(terminals) == 11
    assert all(item.run_reserved_usd <= Decimal("0.10") for item in terminals)
    assert max(item.total_reserved_usd for item in terminals) <= Decimal(1)
    assert not (output / "stage-gate-final.json").exists()
    assert model2_preflight["matrix_sha256"] == model1_preflight["matrix_sha256"]
    assert model2_preflight["prompt_contract_sha256"] == model1_preflight["prompt_contract_sha256"]
    comparison = json.loads((output / "cross-model-comparison.json").read_text(encoding="utf-8"))
    assert comparison["models_pooled"] is False
    assert comparison["single_cluster_per_model"] is True
    assert comparison["statistical_significance"] is None
    assert comparison["bootstrap_ci"] is None
    assert comparison["model1"]["model_id"] == "gpt-5.6-luna"
    assert comparison["model2"]["model_id"] == SECOND_MODEL_ID
    assert comparison["model1"]["observed"] == 11
    assert comparison["model2"]["observed"] == 11
    c1 = comparison["c1_direction"]
    assert c1["consistent"] is (
        c1["shared_off_direction_model1"] == c1["shared_off_direction_model2"]
        and c1["shared_on_direction_model1"] == c1["shared_on_direction_model2"]
    )
    for pair_name in ("m2_direction", "a1_direction"):
        pair = comparison[pair_name]
        assert pair["consistent"] is (pair["model1_direction"] == pair["model2_direction"])
    assert comparison["formal_metrics"] == {
        "uea": "not_available",
        "alr": "not_available",
        "rir_1": "not_available",
        "rir_3": "not_available",
        "provenance": "not_available",
    }
    assert comparison["sample_expansion_recommended"] is True


def test_t16e_cli_reads_the_second_api_key_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name, value in {
        "SKILLFLOW_SECOND_PROVIDER": "openai",
        "SKILLFLOW_SECOND_MODEL_ID": SECOND_MODEL_ID,
        "SKILLFLOW_MAX_USD": "1",
        "SKILLFLOW_LIVE_APPROVED": "1",
    }.items():
        monkeypatch.setenv(name, value)
    reads = 0

    def read_once() -> SecretStr:
        nonlocal reads
        reads += 1
        return SecretStr("different-test-only-secret")

    class _TransportContext:
        def __enter__(self) -> object:
            return object()

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc_value: BaseException | None,
            traceback: object,
        ) -> None:
            del exc_type, exc_value, traceback

    monkeypatch.setattr(task_success_canary_cli, "read_api_key", read_once)
    monkeypatch.setattr(
        task_success_canary_cli,
        "managed_httpx2_transport",
        _TransportContext,
    )
    monkeypatch.setattr(
        task_success_canary_cli,
        "OpenAIResponsesClient",
        lambda _secret, _transport: TaskSuccessMockLiveClient(),
    )
    main_t16e = task_success_canary_cli.main_t16e

    main_t16e(ROOT, tmp_path / "cli-model2-attempt")

    assert reads == 1


def test_t16e_step_limit_persists_all_sixteen_responses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *_args, **_kwargs: pytest.fail("unexpected real network"),
    )
    client = _EndlessSecondModelClient()
    environment = task_success_canary_preflight.load_t16e_environment(
        {
            "SKILLFLOW_SECOND_PROVIDER": "openai",
            "SKILLFLOW_SECOND_MODEL_ID": SECOND_MODEL_ID,
            "SKILLFLOW_MAX_USD": "1",
            "SKILLFLOW_LIVE_APPROVED": "1",
        }
    )
    output = tmp_path / "step-limit"

    summary = task_success_canary_run.execute_t16e_canary_run(
        T16D2CanaryRunRequest(ROOT, output, environment),
        client,
    )

    events = load_canary_usage_events(output / "actual-usage-journal.jsonl")
    responses = tuple(item for item in events if item.event_type == "response")
    terminal = events[-1]
    assert client.calls == 16
    assert summary.status == "BLOCKED"
    assert summary.observed == 0
    assert len(responses) == 16
    assert terminal.terminal_status is LiveTrialTerminalStatus.STEP_LIMIT_EXHAUSTED
    assert terminal.actual_usage_status is ActualUsageStatus.COMPLETE
    assert terminal.observed_token_usage is not None
    assert terminal.observed_token_usage.input_tokens == 1_600


def test_t16e_model_revision_drift_saves_response_then_stops(
    tmp_path: Path,
) -> None:
    environment = task_success_canary_preflight.load_t16e_environment(
        {
            "SKILLFLOW_SECOND_PROVIDER": "openai",
            "SKILLFLOW_SECOND_MODEL_ID": SECOND_MODEL_ID,
            "SKILLFLOW_MAX_USD": "1",
            "SKILLFLOW_LIVE_APPROVED": "1",
        }
    )
    output = tmp_path / "model-drift"
    client = _DriftingSecondModelClient()

    summary = task_success_canary_run.execute_t16e_canary_run(
        T16D2CanaryRunRequest(ROOT, output, environment),
        client,
    )

    events = load_canary_usage_events(output / "actual-usage-journal.jsonl")
    assert client.calls == 1
    assert summary.status == "BLOCKED"
    assert summary.observed == 0
    assert summary.stop_reason is not None
    assert summary.stop_reason.value == "model_revision_changed"
    assert events[0].event_type == "response"
    assert events[0].model_revision == "gpt-5.5"
    assert events[-1].observed_token_usage is not None


def test_t16e_config_and_comparison_schemas_are_registered() -> None:
    filenames = {item.filename for item in schema_documents()}

    assert "t16e-live-config.schema.json" in filenames
    assert "t16e-cross-model-comparison.schema.json" in filenames
