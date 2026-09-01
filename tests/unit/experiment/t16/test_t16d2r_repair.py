import hashlib
import json
import socket
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError
from tests.unit.experiment.t16.test_t16d2_live_agent import _b0_execution

from skillflow.experiment.t16.budget import BudgetLedger, CallReservation
from skillflow.experiment.t16.live_agent_calls import LiveAgentClient
from skillflow.experiment.t16.live_run_models import LiveGatewayCrashError
from skillflow.experiment.t16.live_usage_store import (
    ActualUsageStatus,
    LiveTrialTerminalStatus,
    LiveUsageJournal,
    LiveUsageJournalEvent,
    LiveUsageStoreError,
    load_live_usage_events,
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
from skillflow.experiment.t16.provider import TokenUsage
from skillflow.experiment.t16.task_success_live_agent import (
    TaskSuccessLiveExecutionOptions,
    execute_task_success_live_trial,
)
from skillflow.experiment.t16.task_success_live_config import (
    T16D2R_CONFIG_SHA256,
    T16D2R_PROTOCOL_SHA256,
    build_t16d2_live_config,
    build_t16d2r_live_config,
)
from skillflow.experiment.t16.task_success_live_design import (
    build_task_success_live_design,
)
from skillflow.experiment.t16.task_success_live_mock import TaskSuccessMockLiveClient
from skillflow.experiment.t16.task_success_live_models import T16D2RawTrialRecord
from skillflow.experiment.t16.task_success_live_preflight import (
    T16D2Environment,
    load_t16d2_environment,
    load_t16d2r_inputs,
)
from skillflow.experiment.t16.task_success_live_run import (
    T16D2RunRequest,
    T16D2StopReason,
    execute_t16d2r_run,
)
from skillflow.experiment.t16.task_success_live_stage import evaluate_t16d2_stage_gate

ROOT = Path(__file__).parents[4]
T16 = ROOT / "experiments" / "t16"
OLD_ATTEMPT = ROOT / "runs" / "t16d2-v3-live-20260829-01" / "attempt-01"
OLD_ATTEMPT_HASHES = {
    "bridge-report.json": "79af70b489dce77d1d45c30e9da012ef74c4124963be17e41c4e84064245c124",
    "budget-journal.jsonl": "bbd31d17e0d9f60e0b2cf5623cf64d81a6dd7540d4373d316041156cf86767e2",
    "checkpoint-007.json": "14cca080112bf406023f7cf5b93f48d174eb6b9457296abb9d20d941dbaa6806",
    "preflight.json": "7b46d8c75e752aa7ef7007079fd26459da0131f77eadecdc4c192a7b4d3cc50c",
    "raw-trials.jsonl": "911158a920488c50cd9676ede396e30c8c88d90f05e882e7efce8025613c34d6",
    "run-summary.json": "a9b24ae89ba0a5abe17c8eff9948baeb7e9be4260332f4b8fae5e608e8595348",
    "stage-gate-canary.json": "9ec886d238089b41ed5390f8271f9b62edbc313ee3b8fa0502789f184e02c009",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _environment() -> T16D2Environment:
    return load_t16d2_environment(
        {
            "SKILLFLOW_PROVIDER": "openai",
            "SKILLFLOW_MODEL_ID": "gpt-5.6-luna",
            "SKILLFLOW_MAX_USD": "3",
            "SKILLFLOW_LIVE_APPROVED": "1",
        }
    )


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
class ProviderErrorClient(LiveAgentClient):
    calls: int = 0

    def create(self, call: OpenAIResponsesCall) -> OpenAIResponsesTurn:
        self.calls += 1
        raise OpenAIResponsesError(
            OpenAIResponsesErrorKind.PROVIDER_ERROR,
            status_code=400,
            provider_type="invalid_request_error",
        )


@dataclass
class GatewayCrashClient(LiveAgentClient):
    calls: int = 0

    def create(self, call: OpenAIResponsesCall) -> OpenAIResponsesTurn:
        self.calls += 1
        raise LiveGatewayCrashError


def test_v31_changes_only_version_identity_and_agent_step_limit() -> None:
    old_path = T16 / "preregistration_task_success_v3.yaml"
    new_path = T16 / "preregistration_task_success_v3_1.yaml"
    old = yaml.safe_load(old_path.read_text(encoding="utf-8"))
    new = yaml.safe_load(new_path.read_text(encoding="utf-8"))

    assert new["schema_version"] == "0.3.1"
    assert new["protocol_version"] == "3.1"
    assert new["id"] == "t16-task-success-bridge-preregistration-v3.1"
    assert new["budget"]["max_agent_turns"] == 16
    assert _sha256(new_path) == T16D2R_PROTOCOL_SHA256

    new_normalized = dict(new)
    new_normalized["schema_version"] = "0.3"
    new_normalized["id"] = old["id"]
    new_normalized.pop("protocol_version")
    new_normalized["budget"] = dict(new_normalized["budget"])
    new_normalized["budget"]["max_agent_turns"] = 8
    assert old == new_normalized

    assert _sha256(T16 / "matrix_task_success_smoke_v3.yaml") == (
        "695560d3494ca037fa19b84b2bcb9daa5f4f74016da4396ac450f07538e54b56"
    )


def test_v31_live_config_has_16_steps_and_preserves_all_other_execution_factors() -> None:
    old = build_t16d2_live_config(ROOT)
    revised = build_t16d2r_live_config(ROOT)

    assert revised.schema_version == "0.2"
    assert revised.id == "t16d2r-v3.1-gpt-5.6-luna"
    assert T16D2R_CONFIG_SHA256 == (
        "6eedc1313c8ed84d39a7e5788746912ea36dac94c22f29f3331851a6e6c3fe56"
    )
    assert revised.budget.max_agent_turns == 16
    assert revised.provider == old.provider
    assert (
        revised.model_copy(
            update={
                "schema_version": old.schema_version,
                "id": old.id,
                "budget": revised.budget.model_copy(update={"max_agent_turns": 8}),
            }
        )
        == old
    )


def test_m2_target_completes_inside_revised_16_step_boundary() -> None:
    inputs = load_t16d2r_inputs(ROOT)
    config = build_t16d2r_live_config(ROOT)
    trial = next(
        item
        for item in inputs.matrix.trials
        if item.condition_id == "m2-target"
        and item.semantic_instance_id.endswith("v01")
        and item.repeat_index == 1
    )
    design = build_task_success_live_design(inputs, trial)
    client = TaskSuccessMockLiveClient()

    execution = execute_task_success_live_trial(
        design,
        next(item for item in inputs.registry.conditions if item.condition_id == "m2-target"),
        config,
        client,
        BudgetLedger(config.budget).begin_run(),
        TaskSuccessLiveExecutionOptions(
            run_id="t16d2r-m2-target",
            created_at=datetime(2026, 8, 29, tzinfo=UTC),
            phase_contract_sha256="3" * 64,
        ),
    )

    assert tuple(item.session_index for item in execution.record.sessions) == (0, 1, 2, 3)
    assert execution.record.result.api_call_count <= 16
    assert execution.record.result.task_success is True


def test_revised_runner_rejects_step_17_before_client_and_saves_usage_in_finally(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        detail = "unexpected real network"
        raise AssertionError(detail)

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(socket.socket, "connect", fail_network)
    output = tmp_path / "new-v31-attempt"
    client = EndlessB0ToolClient()

    summary = execute_t16d2r_run(
        T16D2RunRequest(ROOT, output, _environment()),
        client,
    )

    assert client.calls == 16
    assert summary.observed == 0
    assert summary.stop_reason is T16D2StopReason.BUDGET_LIMIT
    assert summary.stop_detail == "agent_turns"
    events = load_live_usage_events(output / "actual-usage-journal.jsonl")
    terminal = events[-1]
    assert len(tuple(item for item in events if item.event_type == "response")) == 16
    assert terminal.event_type == "terminal"
    assert terminal.terminal_status is LiveTrialTerminalStatus.STEP_LIMIT_EXHAUSTED
    assert terminal.api_call_count == 16
    assert terminal.response_count == 16
    assert terminal.actual_usage_status is ActualUsageStatus.COMPLETE
    assert terminal.observed_token_usage is not None
    assert terminal.observed_token_usage.input_tokens == 1600
    assert terminal.observed_estimated_cost_usd is not None
    assert terminal.total_reserved_usd > 0


def test_missing_actual_usage_is_na_not_zero(tmp_path: Path) -> None:
    config = build_t16d2r_live_config(ROOT)
    journal = LiveUsageJournal(
        tmp_path / "actual-usage-journal.jsonl",
        config,
        protocol_id="t16-task-success-bridge-preregistration-v3.1",
    )
    journal.open_new()
    tracker = journal.start_trial("trial-without-response")
    reserved = (
        BudgetLedger(config.budget)
        .begin_run()
        .authorize_call(
            CallReservation(
                estimated_cost_usd=Decimal("0.001"),
                max_output_tokens=512,
            )
        )
    )
    tracker.record_attempt(reserved)
    tracker.finalize(LiveTrialTerminalStatus.PARTIAL, "provider_error")

    terminal = load_live_usage_events(journal.path)[-1]
    assert terminal.actual_usage_status is ActualUsageStatus.NOT_AVAILABLE
    assert terminal.observed_token_usage is None
    assert terminal.observed_estimated_cost_usd is None
    assert terminal.api_call_count == 1
    assert terminal.total_reserved_usd == Decimal("0.001")


def test_partial_usage_preserves_known_response_without_claiming_complete_total(
    tmp_path: Path,
) -> None:
    config = build_t16d2r_live_config(ROOT)
    journal = LiveUsageJournal(
        tmp_path / "actual-usage-journal.jsonl",
        config,
        protocol_id="t16-task-success-bridge-preregistration-v3.1",
    )
    journal.open_new()
    tracker = journal.start_trial("partial-usage")
    first = (
        BudgetLedger(config.budget)
        .begin_run()
        .authorize_call(CallReservation(estimated_cost_usd=Decimal("0.001"), max_output_tokens=512))
    )
    tracker.record_attempt(first)
    tracker.record_response(_usage(), Decimal("0.0001"))
    second = first.authorize_call(
        CallReservation(estimated_cost_usd=Decimal("0.001"), max_output_tokens=512)
    )
    tracker.record_attempt(second)
    tracker.finalize(LiveTrialTerminalStatus.PARTIAL, "provider_error")

    terminal = load_live_usage_events(journal.path)[-1]
    assert terminal.actual_usage_status is ActualUsageStatus.PARTIAL
    assert terminal.observed_token_usage == _usage()
    assert terminal.observed_estimated_cost_usd == Decimal("0.0001")
    assert terminal.api_call_count == 2
    assert terminal.response_count == 1
    assert journal.config_sha256 == terminal.config_sha256


def test_usage_journal_rejects_reopen_duplicate_terminal_and_post_final_update(
    tmp_path: Path,
) -> None:
    config = build_t16d2r_live_config(ROOT)
    path = tmp_path / "actual-usage-journal.jsonl"
    journal = LiveUsageJournal(
        path,
        config,
        protocol_id="t16-task-success-bridge-preregistration-v3.1",
    )
    with pytest.raises(LiveUsageStoreError, match="尚未打开"):
        journal.start_trial("trial-1")
    journal.open_new()
    tracker = journal.start_trial("trial-1")
    tracker.finalize(LiveTrialTerminalStatus.PARTIAL, "provider_error")

    with pytest.raises(LiveUsageStoreError, match="已存在终态"):
        journal.start_trial("trial-1")
    with pytest.raises(LiveUsageStoreError, match="已终结"):
        tracker.record_attempt(BudgetLedger(config.budget))
    duplicate = LiveUsageJournal(
        path,
        config,
        protocol_id="t16-task-success-bridge-preregistration-v3.1",
    )
    with pytest.raises(LiveUsageStoreError, match="无法新建"):
        duplicate.open_new()


@pytest.mark.parametrize(
    "changes",
    [
        {"response_count": 2},
        {"actual_usage_status": "not_available"},
        {
            "response_count": 0,
            "actual_usage_status": "not_available",
        },
        {"observed_token_usage": None},
        {"observed_estimated_cost_usd": None},
        {"terminal_status": "completed"},
        {"event_type": "terminal", "terminal_status": None},
    ],
)
def test_usage_event_rejects_ambiguous_or_inconsistent_na(changes: dict[str, object]) -> None:
    payload: dict[str, object] = {
        "sequence": 1,
        "event_type": "response",
        "protocol_id": "protocol-v3.1",
        "config_id": "config-v3.1",
        "config_sha256": "a" * 64,
        "trial_id": "trial-1",
        "api_call_count": 1,
        "response_count": 1,
        "total_reserved_usd": "0.001",
        "run_reserved_usd": "0.001",
        "actual_usage_status": "complete",
        "observed_token_usage": _usage().model_dump(mode="json"),
        "observed_estimated_cost_usd": "0.0001",
    }
    payload.update(changes)

    with pytest.raises(ValidationError):
        LiveUsageJournalEvent.model_validate(payload)


def test_usage_loader_rejects_non_contiguous_sequence(tmp_path: Path) -> None:
    path = tmp_path / "broken-usage.jsonl"
    event = LiveUsageJournalEvent(
        sequence=2,
        event_type="terminal",
        protocol_id="protocol-v3.1",
        config_id="config-v3.1",
        config_sha256="a" * 64,
        trial_id="trial-1",
        api_call_count=0,
        response_count=0,
        total_reserved_usd=Decimal(0),
        run_reserved_usd=Decimal(0),
        actual_usage_status=ActualUsageStatus.NOT_AVAILABLE,
        observed_token_usage=None,
        observed_estimated_cost_usd=None,
        terminal_status=LiveTrialTerminalStatus.PARTIAL,
        stop_detail="provider_error",
    )
    path.write_text(f"{event.model_dump_json()}\n", encoding="utf-8")

    with pytest.raises(LiveUsageStoreError, match="sequence"):
        load_live_usage_events(path)


@pytest.mark.parametrize(
    ("client", "expected_stop", "expected_detail"),
    [
        (
            ProviderErrorClient(),
            T16D2StopReason.INFRASTRUCTURE_RATE,
            "provider_error",
        ),
        (
            GatewayCrashClient(),
            T16D2StopReason.GATEWAY_CRASH,
            "gateway_crash",
        ),
    ],
)
def test_provider_error_and_gateway_exception_save_na_usage_in_finally(
    tmp_path: Path,
    client: ProviderErrorClient | GatewayCrashClient,
    expected_stop: T16D2StopReason,
    expected_detail: str,
) -> None:
    output = tmp_path / expected_detail

    summary = execute_t16d2r_run(
        T16D2RunRequest(ROOT, output, _environment()),
        client,
    )

    terminal = load_live_usage_events(output / "actual-usage-journal.jsonl")[-1]
    assert summary.stop_reason is expected_stop
    assert client.calls == 1
    assert terminal.terminal_status is LiveTrialTerminalStatus.PARTIAL
    assert terminal.stop_detail == expected_detail
    assert terminal.api_call_count == 1
    assert terminal.actual_usage_status is ActualUsageStatus.NOT_AVAILABLE
    assert terminal.observed_token_usage is None
    assert terminal.observed_estimated_cost_usd is None
    assert terminal.total_reserved_usd > 0


def test_original_v3_attempt_hashes_are_byte_identical() -> None:
    assert {
        name: _sha256(OLD_ATTEMPT / name) for name in sorted(OLD_ATTEMPT_HASHES)
    } == OLD_ATTEMPT_HASHES


def test_stage_gate_rejects_cross_protocol_phase_contract_merge(tmp_path: Path) -> None:
    execution = _b0_execution()
    original = T16D2RawTrialRecord(
        task_success_spec_id=execution.task_success_spec_id,
        provider_model_revisions=execution.provider_model_revisions,
        platform_evidence_snapshot=execution.snapshot,
        live_trial=execution.record,
    )
    revised = original.model_copy(
        update={
            "live_trial": original.live_trial.model_copy(update={"phase_contract_sha256": "4" * 64})
        }
    )
    raw_path = tmp_path / "mixed.jsonl"
    raw_path.write_text("", encoding="utf-8")
    registry = load_t16d2r_inputs(ROOT).registry

    gate = evaluate_t16d2_stage_gate(
        "canary",
        (original, revised),
        registry,
        2,
        raw_path,
    )

    assert gate.passed is False
    assert "phase_contract_mismatch" in gate.reasons
