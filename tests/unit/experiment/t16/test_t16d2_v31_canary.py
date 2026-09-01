import json
import socket
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import SecretStr

from skillflow.experiment.t16 import task_success_canary_cli, task_success_live_config
from skillflow.experiment.t16.live_agent_calls import LiveAgentClient
from skillflow.experiment.t16.live_canary_usage import (
    ActualUsageStatus,
    LiveTrialTerminalStatus,
    load_canary_usage_events,
)
from skillflow.experiment.t16.openai_response_models import (
    ApiFunctionCall,
    OpenAIResponsesCall,
)
from skillflow.experiment.t16.openai_responses import OpenAIResponsesTurn
from skillflow.experiment.t16.provider import TokenUsage
from skillflow.experiment.t16.task_success_canary_preflight import (
    T16D2CanaryEnvironmentError,
    load_t16d2r_canary_environment,
    load_t16d2r_canary_inputs,
)
from skillflow.experiment.t16.task_success_canary_run import (
    T16D2CanaryRunRequest,
    execute_t16d2r_canary_run,
)
from skillflow.experiment.t16.task_success_live_mock import TaskSuccessMockLiveClient
from skillflow.experiment.t16.task_success_live_models import T16D2StopReason
from skillflow.experiment.t16.task_success_live_store import load_t16d2_raw_records

ROOT = Path(__file__).parents[4]


def _block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        detail = "unexpected real network"
        raise AssertionError(detail)

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(socket.socket, "connect", fail_network)


def _usage() -> TokenUsage:
    return TokenUsage(
        input_tokens=100,
        cached_input_tokens=20,
        cache_write_tokens=0,
        output_tokens=8,
        reasoning_tokens=4,
    )


@dataclass
class EndlessB0ToolClient(LiveAgentClient):
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
            token_usage=_usage(),
            latency_ms=1,
        )


@dataclass
class DriftingModelClient(LiveAgentClient):
    calls: int = 0

    def create(self, call: OpenAIResponsesCall) -> OpenAIResponsesTurn:
        self.calls += 1
        return OpenAIResponsesTurn(
            response_id="response-drift",
            model_revision="gpt-5.6-luna-drifted",
            status="completed",
            function_calls=(),
            continuation_items=(),
            output_text="",
            refusal=True,
            token_usage=_usage(),
            latency_ms=1,
        )


def test_v31_canary_config_applies_only_the_authorized_phase_budget() -> None:
    base = task_success_live_config.build_t16d2r_live_config(ROOT)

    canary = task_success_live_config.build_t16d2r_canary_config(ROOT)

    assert base.id == "t16d2r-v3.1-gpt-5.6-luna"
    assert base.budget.max_total_usd == Decimal(3)
    assert canary.id == "t16d2r-v3.1-canary-gpt-5.6-luna"
    assert task_success_live_config.T16D2R_CANARY_CONFIG_SHA256 == (
        "0ab28b3f0907a6cfcf6a126af67f23ed9a6f646d00baea02cc16c548fcd20ba2"
    )
    assert canary.provider == base.provider
    assert canary.budget.max_total_usd == Decimal("0.25")
    assert canary.budget.max_cost_per_run_usd == Decimal("0.05")
    assert canary.budget.max_agent_turns == 16
    assert canary.budget.max_output_tokens_per_turn == 512
    assert canary.budget.max_retries == 1
    assert canary.smoke_max_total_usd == Decimal("0.25")


def test_v31_canary_schedule_is_exactly_the_frozen_11_and_pairs_are_complete() -> None:
    prepared = load_t16d2r_canary_inputs(ROOT)

    assert len(prepared.schedule) == 11
    assert len({item.trial_id for item in prepared.schedule}) == 11
    assert tuple(item.condition_id for item in prepared.schedule) == (
        "b0",
        "g0",
        "c1-p00",
        "c1-p01",
        "c1-p10",
        "c1-p11",
        "m2-control",
        "m2-target",
        "a1-claim",
        "a1-neutralized",
        "a2-structured-confirmation",
    )
    assert prepared.pairs_complete is True
    assert prepared.c1_harm_selector_shared is True


def test_v31_canary_runs_only_11_and_persists_response_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _block_network(monkeypatch)
    output = tmp_path / "attempt-01"
    environment = load_t16d2r_canary_environment(
        {
            "SKILLFLOW_PROVIDER": "openai",
            "SKILLFLOW_MODEL_ID": "gpt-5.6-luna",
            "SKILLFLOW_MAX_USD": "0.25",
            "SKILLFLOW_LIVE_APPROVED": "1",
        }
    )

    summary = execute_t16d2r_canary_run(
        T16D2CanaryRunRequest(ROOT, output, environment),
        TaskSuccessMockLiveClient(),
    )

    records = load_t16d2_raw_records(output / "raw-trials.jsonl")
    assert summary.status == "PASSED"
    assert summary.scheduled == 11
    assert summary.observed == 11
    assert summary.unrun == 0
    assert summary.canary_gate_passed is True
    assert summary.task_success_result_count == 11
    assert summary.not_evaluable_assertion_count == 0
    assert summary.pairs_complete is True
    assert summary.c1_harm_selector_shared is True
    assert summary.receipt_coverage_complete is True
    assert len(records) == 11
    assert tuple(item.live_trial.result.condition_id for item in records) == (
        "b0",
        "g0",
        "c1-p00",
        "c1-p01",
        "c1-p10",
        "c1-p11",
        "m2-control",
        "m2-target",
        "a1-claim",
        "a1-neutralized",
        "a2-structured-confirmation",
    )
    events = load_canary_usage_events(output / "actual-usage-journal.jsonl")
    response_events = tuple(item for item in events if item.event_type == "response")
    terminal_events = tuple(item for item in events if item.event_type == "terminal")
    assert len(terminal_events) == 11
    assert all(
        item.terminal_status is LiveTrialTerminalStatus.COMPLETED for item in terminal_events
    )
    assert all(item.session_index is not None for item in response_events)
    assert all(item.agent_step is not None for item in response_events)
    assert all(item.provider == "openai" for item in response_events)
    assert all(item.model_id == "gpt-5.6-luna" for item in response_events)
    assert all(item.model_revision == "gpt-5.6-luna" for item in response_events)
    assert all(item.response_token_usage is not None for item in response_events)
    assert all(item.response_estimated_cost_usd is not None for item in response_events)
    m2_target = next(item for item in summary.trials if item.condition_id == "m2-target")
    assert m2_target.agent_steps <= 16
    assert (output / "stage-gate-canary.json").is_file()
    assert not (output / "stage-gate-final.json").exists()


def test_v31_canary_step_limit_saves_partial_trial_usage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _block_network(monkeypatch)
    client = EndlessB0ToolClient()
    environment = load_t16d2r_canary_environment(
        {
            "SKILLFLOW_PROVIDER": "openai",
            "SKILLFLOW_MODEL_ID": "gpt-5.6-luna",
            "SKILLFLOW_MAX_USD": "0.25",
            "SKILLFLOW_LIVE_APPROVED": "1",
        }
    )

    summary = execute_t16d2r_canary_run(
        T16D2CanaryRunRequest(ROOT, tmp_path / "partial-attempt", environment),
        client,
    )

    events = load_canary_usage_events(tmp_path / "partial-attempt" / "actual-usage-journal.jsonl")
    responses = tuple(item for item in events if item.event_type == "response")
    terminal = events[-1]
    assert client.calls == 16
    assert summary.status == "BLOCKED"
    assert summary.observed == 0
    assert summary.unrun == 11
    assert terminal.event_type == "terminal"
    assert terminal.terminal_status is LiveTrialTerminalStatus.STEP_LIMIT_EXHAUSTED
    assert terminal.actual_usage_status is ActualUsageStatus.COMPLETE
    assert terminal.api_call_count == 16
    assert terminal.observed_token_usage is not None
    assert terminal.observed_token_usage.input_tokens == 1600
    assert terminal.observed_estimated_cost_usd is not None
    assert tuple(item.agent_step for item in responses) == tuple(range(1, 17))
    assert {item.session_index for item in responses} == {0}


def test_v31_canary_environment_rejects_the_old_three_dollar_cap() -> None:
    with pytest.raises(T16D2CanaryEnvironmentError, match=r"0\.25"):
        load_t16d2r_canary_environment(
            {
                "SKILLFLOW_PROVIDER": "openai",
                "SKILLFLOW_MODEL_ID": "gpt-5.6-luna",
                "SKILLFLOW_MAX_USD": "3",
                "SKILLFLOW_LIVE_APPROVED": "1",
            }
        )


def test_v31_canary_saves_drifting_response_then_stops_before_next_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _block_network(monkeypatch)
    client = DriftingModelClient()
    environment = load_t16d2r_canary_environment(
        {
            "SKILLFLOW_PROVIDER": "openai",
            "SKILLFLOW_MODEL_ID": "gpt-5.6-luna",
            "SKILLFLOW_MAX_USD": "0.25",
            "SKILLFLOW_LIVE_APPROVED": "1",
        }
    )

    summary = execute_t16d2r_canary_run(
        T16D2CanaryRunRequest(ROOT, tmp_path / "drift-attempt", environment),
        client,
    )

    events = load_canary_usage_events(tmp_path / "drift-attempt" / "actual-usage-journal.jsonl")
    assert client.calls == 1
    assert summary.status == "BLOCKED"
    assert summary.stop_reason is T16D2StopReason.MODEL_REVISION_CHANGED
    assert events[0].event_type == "response"
    assert events[0].model_revision == "gpt-5.6-luna-drifted"
    assert events[-1].event_type == "terminal"
    assert events[-1].observed_token_usage == _usage()


def test_v31_canary_cli_reads_api_key_once_and_reuses_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _block_network(monkeypatch)
    for name, value in {
        "SKILLFLOW_PROVIDER": "openai",
        "SKILLFLOW_MODEL_ID": "gpt-5.6-luna",
        "SKILLFLOW_MAX_USD": "0.25",
        "SKILLFLOW_LIVE_APPROVED": "1",
    }.items():
        monkeypatch.setenv(name, value)
    reads = 0

    def read_once() -> SecretStr:
        nonlocal reads
        reads += 1
        return SecretStr("test-only-secret")

    @contextmanager
    def fake_transport() -> Iterator[object]:
        yield object()

    monkeypatch.setattr(task_success_canary_cli, "read_api_key", read_once)
    monkeypatch.setattr(
        task_success_canary_cli,
        "managed_httpx2_transport",
        fake_transport,
    )
    monkeypatch.setattr(
        task_success_canary_cli,
        "OpenAIResponsesClient",
        lambda _secret, _transport: TaskSuccessMockLiveClient(),
    )

    task_success_canary_cli.main(ROOT, tmp_path / "cli-attempt")

    assert reads == 1
