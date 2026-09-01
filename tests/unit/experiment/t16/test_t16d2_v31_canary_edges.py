import socket
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from skillflow.experiment.t16.budget import BudgetLedger, CallReservation
from skillflow.experiment.t16.live_agent_calls import (
    ActualResponseUsage,
    LiveAgentClient,
)
from skillflow.experiment.t16.live_canary_usage import (
    CanaryUsageJournalEvent,
    LiveCanaryMetadataDriftError,
    LiveCanaryUsageJournal,
    LiveCanaryUsageStoreError,
    LiveTrialTerminalStatus,
    load_canary_usage_events,
)
from skillflow.experiment.t16.live_canary_usage_models import CanaryUsageSnapshot
from skillflow.experiment.t16.live_run_models import LiveGatewayCrashError
from skillflow.experiment.t16.openai_response_models import OpenAIResponsesCall
from skillflow.experiment.t16.openai_responses import (
    OpenAIResponsesError,
    OpenAIResponsesErrorKind,
    OpenAIResponsesTurn,
)
from skillflow.experiment.t16.provider import TokenUsage
from skillflow.experiment.t16.task_success_canary_preflight import (
    T16D2CanaryEnvironmentError,
    load_t16d2r_canary_environment,
)
from skillflow.experiment.t16.task_success_canary_run import (
    T16D2CanaryRunError,
    T16D2CanaryRunRequest,
    execute_t16d2r_canary_run,
)
from skillflow.experiment.t16.task_success_live_config import (
    T16D2R_PROTOCOL_ID,
    build_t16d2r_canary_config,
)
from skillflow.experiment.t16.task_success_live_models import T16D2StopReason
from skillflow.experiment.t16.task_success_live_preflight import T16D2Environment

ROOT = Path(__file__).parents[4]


def _usage() -> TokenUsage:
    return TokenUsage(
        input_tokens=10,
        cached_input_tokens=2,
        cache_write_tokens=0,
        output_tokens=3,
        reasoning_tokens=1,
    )


def _environment() -> T16D2Environment:
    return load_t16d2r_canary_environment(
        {
            "SKILLFLOW_PROVIDER": "openai",
            "SKILLFLOW_MODEL_ID": "gpt-5.6-luna",
            "SKILLFLOW_MAX_USD": "0.25",
            "SKILLFLOW_LIVE_APPROVED": "1",
        }
    )


def _snapshot(trial_id: str, event_type: str = "terminal") -> CanaryUsageSnapshot:
    return CanaryUsageSnapshot(
        event_type=event_type,  # type: ignore[arg-type]
        trial_id=trial_id,
        condition_id="b0",
        session_index=None,
        agent_step=None,
        provider="openai",
        model_id="gpt-5.6-luna",
        model_revision=None,
        api_call_count=0,
        response_count=0,
        total_reserved_usd=Decimal(0),
        run_reserved_usd=Decimal(0),
        response_token_usage=None,
        response_estimated_cost_usd=None,
        observed_token_usage=None,
        observed_estimated_cost_usd=None,
        completed_session_indices=(),
        terminal_status=LiveTrialTerminalStatus.PARTIAL,
        stop_detail="partial",
    )


def _response_payload() -> dict[str, object]:
    return {
        "sequence": 1,
        "recorded_at": datetime(2026, 8, 30, tzinfo=UTC),
        "event_type": "response",
        "protocol_id": T16D2R_PROTOCOL_ID,
        "config_id": "t16d2r-v3.1-canary-gpt-5.6-luna",
        "config_sha256": "a" * 64,
        "trial_id": "live--trial-1",
        "condition_id": "b0",
        "session_index": 0,
        "agent_step": 1,
        "provider": "openai",
        "model_id": "gpt-5.6-luna",
        "model_revision": "gpt-5.6-luna",
        "api_call_count": 1,
        "response_count": 1,
        "total_reserved_usd": "0.001",
        "run_reserved_usd": "0.001",
        "response_token_usage": _usage().model_dump(mode="json"),
        "response_estimated_cost_usd": "0.0001",
        "actual_usage_status": "complete",
        "observed_token_usage": _usage().model_dump(mode="json"),
        "observed_estimated_cost_usd": "0.0001",
        "completed_session_indices": [],
        "terminal_status": None,
        "stop_detail": None,
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"response_count": 2},
        {"actual_usage_status": "not_available"},
        {"response_count": 0, "actual_usage_status": "not_available"},
        {
            "response_count": 0,
            "actual_usage_status": "not_available",
            "observed_token_usage": None,
        },
        {"observed_token_usage": None},
        {"completed_session_indices": [0, 0]},
        {"session_index": None},
        {"terminal_status": "completed"},
        {
            "event_type": "terminal",
            "terminal_status": None,
            "response_token_usage": None,
            "response_estimated_cost_usd": None,
        },
        {
            "event_type": "terminal",
            "terminal_status": "partial",
            "response_estimated_cost_usd": None,
        },
    ],
)
def test_canary_usage_event_rejects_ambiguous_na(changes: dict[str, object]) -> None:
    payload = _response_payload()
    payload.update(changes)

    with pytest.raises(ValidationError):
        CanaryUsageJournalEvent.model_validate(payload)


def test_canary_usage_journal_rejects_unsafe_lifecycle_and_corruption(
    tmp_path: Path,
) -> None:
    config = build_t16d2r_canary_config(ROOT)
    path = tmp_path / "usage.jsonl"
    journal = LiveCanaryUsageJournal(path, config, T16D2R_PROTOCOL_ID)
    with pytest.raises(LiveCanaryUsageStoreError, match="尚未打开"):
        journal.start_trial("trial-before-open", "b0")
    with pytest.raises(LiveCanaryUsageStoreError, match="尚未打开"):
        journal.append_snapshot(_snapshot("trial-before-open"))
    journal.open_new()
    with pytest.raises(LiveCanaryUsageStoreError, match="无法新建"):
        journal.open_new()
    tracker = journal.start_trial("trial-1", "b0")
    tracker.finalize(LiveTrialTerminalStatus.PARTIAL, "partial")
    with pytest.raises(LiveCanaryUsageStoreError, match="已存在终态"):
        journal.start_trial("trial-1", "b0")
    with pytest.raises(LiveCanaryUsageStoreError, match="已存在终态"):
        journal.append_snapshot(_snapshot("trial-1"))
    assert str(LiveCanaryUsageStoreError("safe")) == "safe"
    assert str(LiveCanaryMetadataDriftError("safe")) == "safe"

    with pytest.raises(LiveCanaryUsageStoreError, match="无法读取"):
        load_canary_usage_events(tmp_path / "missing.jsonl")
    event = load_canary_usage_events(path)[0]
    broken = tmp_path / "broken.jsonl"
    broken.write_text(
        f"{event.model_copy(update={'sequence': 2}).model_dump_json()}\n",
        encoding="utf-8",
    )
    with pytest.raises(LiveCanaryUsageStoreError, match="sequence"):
        load_canary_usage_events(broken)

    after_terminal = tmp_path / "after-terminal.jsonl"
    after_terminal.write_text(
        f"{event.model_dump_json()}\n"
        f"{event.model_copy(update={'sequence': 2}).model_dump_json()}\n",
        encoding="utf-8",
    )
    with pytest.raises(LiveCanaryUsageStoreError, match="终态后"):
        load_canary_usage_events(after_terminal)

    other = event.model_copy(
        update={"sequence": 2, "trial_id": "trial-2", "config_id": "other-config"}
    )
    mixed = tmp_path / "mixed.jsonl"
    mixed.write_text(
        f"{event.model_dump_json()}\n{other.model_dump_json()}\n",
        encoding="utf-8",
    )
    with pytest.raises(LiveCanaryUsageStoreError, match="合同身份"):
        load_canary_usage_events(mixed)


def test_canary_usage_tracker_rejects_session_and_metadata_drift(tmp_path: Path) -> None:
    config = build_t16d2r_canary_config(ROOT)
    journal = LiveCanaryUsageJournal(tmp_path / "usage.jsonl", config, T16D2R_PROTOCOL_ID)
    journal.open_new()
    tracker = journal.start_trial("trial-1", "b0")
    with pytest.raises(LiveCanaryUsageStoreError, match="Session"):
        tracker.record_attempt(BudgetLedger(config.budget))
    with pytest.raises(LiveCanaryUsageStoreError, match="元数据"):
        tracker.record_response(_usage(), Decimal("0.0001"))
    with pytest.raises(LiveCanaryUsageStoreError, match="Session"):
        tracker.record_detailed_response(
            ActualResponseUsage(
                _usage(), Decimal("0.0001"), "openai", "gpt-5.6-luna", "gpt-5.6-luna"
            )
        )
    tracker.activate_session(0)
    with pytest.raises(LiveCanaryUsageStoreError, match="尚未完成"):
        tracker.activate_session(1)
    with pytest.raises(LiveCanaryUsageStoreError, match="错配"):
        tracker.complete_session(1)
    budget = BudgetLedger(config.budget).authorize_call(
        CallReservation(estimated_cost_usd=Decimal("0.001"), max_output_tokens=512)
    )
    tracker.record_attempt(budget)
    with pytest.raises(LiveCanaryMetadataDriftError, match="revision"):
        tracker.record_detailed_response(
            ActualResponseUsage(
                _usage(),
                Decimal("0.0001"),
                "openai",
                "gpt-5.6-luna",
                "gpt-5.6-luna-drifted",
            )
        )
    tracker.complete_session(0)
    with pytest.raises(LiveCanaryUsageStoreError, match="重复"):
        tracker.complete_session(0)
    tracker.finalize(LiveTrialTerminalStatus.PARTIAL, "metadata_drift")
    with pytest.raises(LiveCanaryUsageStoreError, match="已终结"):
        tracker.record_attempt(budget)


@dataclass
class FailingClient(LiveAgentClient):
    kind: OpenAIResponsesErrorKind
    calls: int = 0

    def create(self, call: OpenAIResponsesCall) -> OpenAIResponsesTurn:
        self.calls += 1
        status = 429 if self.kind is OpenAIResponsesErrorKind.RATE_LIMIT else 504
        if self.kind is OpenAIResponsesErrorKind.PROVIDER_ERROR:
            status = 400
        raise OpenAIResponsesError(self.kind, status_code=status)


@dataclass
class CrashingClient(LiveAgentClient):
    calls: int = 0

    def create(self, call: OpenAIResponsesCall) -> OpenAIResponsesTurn:
        self.calls += 1
        raise LiveGatewayCrashError


@pytest.mark.parametrize(
    ("kind", "expected_calls", "detail"),
    [
        (OpenAIResponsesErrorKind.TIMEOUT, 2, "timeout"),
        (OpenAIResponsesErrorKind.RATE_LIMIT, 2, "rate_limit"),
        (OpenAIResponsesErrorKind.PROVIDER_ERROR, 1, "provider_error"),
    ],
)
def test_canary_provider_failures_stop_and_keep_usage_na(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: OpenAIResponsesErrorKind,
    expected_calls: int,
    detail: str,
) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        detail_message = "unexpected real network"
        raise AssertionError(detail_message)

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(socket.socket, "connect", fail_network)
    client = FailingClient(kind)

    summary = execute_t16d2r_canary_run(
        T16D2CanaryRunRequest(ROOT, tmp_path / detail, _environment()),
        client,
    )

    terminal = load_canary_usage_events(tmp_path / detail / "actual-usage-journal.jsonl")[-1]
    assert client.calls == expected_calls
    assert summary.status == "BLOCKED"
    assert summary.stop_reason is T16D2StopReason.INFRASTRUCTURE_RATE
    assert terminal.stop_detail == detail
    assert terminal.observed_token_usage is None
    assert terminal.observed_estimated_cost_usd is None


def test_canary_gateway_crash_and_new_output_guards(tmp_path: Path) -> None:
    client = CrashingClient()
    summary = execute_t16d2r_canary_run(
        T16D2CanaryRunRequest(ROOT, tmp_path / "crash", _environment()),
        client,
    )
    assert client.calls == 1
    assert summary.stop_reason is T16D2StopReason.GATEWAY_CRASH
    assert summary.actual_usage_status.value == "not_available"

    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "marker.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(T16D2CanaryRunError, match="output_root"):
        execute_t16d2r_canary_run(
            T16D2CanaryRunRequest(ROOT, occupied, _environment()),
            client,
        )
    unauthorized = _environment().model_copy(update={"max_total_usd": Decimal("0.24")})
    with pytest.raises(T16D2CanaryRunError, match="预算"):
        execute_t16d2r_canary_run(
            T16D2CanaryRunRequest(ROOT, tmp_path / "budget-mismatch", unauthorized),
            client,
        )


@pytest.mark.parametrize(
    "environment",
    [
        {},
        {
            "SKILLFLOW_PROVIDER": "openai",
            "SKILLFLOW_MODEL_ID": "gpt-5.6-luna",
            "SKILLFLOW_MAX_USD": "bad",
            "SKILLFLOW_LIVE_APPROVED": "1",
        },
        {
            "SKILLFLOW_PROVIDER": "fake",
            "SKILLFLOW_MODEL_ID": "gpt-5.6-luna",
            "SKILLFLOW_MAX_USD": "0.25",
            "SKILLFLOW_LIVE_APPROVED": "1",
        },
        {
            "SKILLFLOW_PROVIDER": "openai",
            "SKILLFLOW_MODEL_ID": "other",
            "SKILLFLOW_MAX_USD": "0.25",
            "SKILLFLOW_LIVE_APPROVED": "1",
        },
        {
            "SKILLFLOW_PROVIDER": "openai",
            "SKILLFLOW_MODEL_ID": "gpt-5.6-luna",
            "SKILLFLOW_MAX_USD": "0.25",
            "SKILLFLOW_LIVE_APPROVED": "0",
        },
    ],
)
def test_canary_environment_is_fail_closed(environment: dict[str, str]) -> None:
    with pytest.raises(T16D2CanaryEnvironmentError):
        load_t16d2r_canary_environment(environment)
