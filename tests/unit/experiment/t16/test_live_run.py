import json
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from skillflow.experiment.t16 import live_phase_contract, live_run
from skillflow.experiment.t16.live_agent_calls import LiveAgentClient
from skillflow.experiment.t16.live_config import T16CLiveConfig
from skillflow.experiment.t16.live_design_models import LiveTrialDesign
from skillflow.experiment.t16.live_run import LivePhaseRequest, execute_live_phase
from skillflow.experiment.t16.live_run_models import (
    LiveGatewayCrashError,
    LivePhase,
    LiveStopReason,
)
from skillflow.experiment.t16.live_store import LiveResultStore
from skillflow.experiment.t16.openai_response_models import JsonObject, OpenAIResponsesCall
from skillflow.experiment.t16.openai_responses import (
    OpenAIResponsesError,
    OpenAIResponsesErrorKind,
    OpenAIResponsesTurn,
)
from skillflow.experiment.t16.preregistration import PreregistrationBindingError
from skillflow.experiment.t16.provider import TokenUsage

ROOT = Path(__file__).parents[4]


def _final_turn(*, valid_schema: bool = True) -> OpenAIResponsesTurn:
    output: JsonObject = {"status": "completed", "summary": "local test completion"}
    return OpenAIResponsesTurn(
        response_id="resp-test",
        model_revision="gpt-5.6-luna",
        status="completed",
        function_calls=(),
        continuation_items=(),
        output_text=json.dumps(output) if valid_schema else "not-json",
        refusal=False,
        token_usage=TokenUsage(
            input_tokens=120,
            cached_input_tokens=0,
            output_tokens=12,
            reasoning_tokens=6,
        ),
        latency_ms=1,
    )


@dataclass
class CompletingClient(LiveAgentClient):
    calls: int = 0
    crash_on_call: int | None = None
    fail_with_timeout: bool = False
    fail_with_provider_status: int | None = None
    schema_reject_on_call: int | None = None
    timeout_calls: tuple[int, ...] = ()
    model_revisions: tuple[str, ...] = ()

    def create(self, call: OpenAIResponsesCall) -> OpenAIResponsesTurn:
        del call
        self.calls += 1
        if self.crash_on_call == self.calls:
            raise LiveGatewayCrashError
        if self.fail_with_timeout:
            raise OpenAIResponsesError(OpenAIResponsesErrorKind.TIMEOUT)
        if self.calls in self.timeout_calls:
            raise OpenAIResponsesError(OpenAIResponsesErrorKind.TIMEOUT)
        if self.fail_with_provider_status is not None:
            raise OpenAIResponsesError(
                OpenAIResponsesErrorKind.PROVIDER_ERROR,
                self.fail_with_provider_status,
                provider_type="invalid_request_error",
                provider_code="unsupported_parameter",
                provider_param="temperature",
            )
        if self.schema_reject_on_call == self.calls:
            return _final_turn(valid_schema=False)
        turn = _final_turn()
        if self.calls <= len(self.model_revisions):
            return replace(turn, model_revision=self.model_revisions[self.calls - 1])
        return turn


def test_live_input_loader_uses_versioned_blind_snapshot() -> None:
    registration, matrix, _config, scenarios = live_run.load_live_phase_inputs(
        LivePhaseRequest(ROOT, Path("unused-versioned-input-output"), LivePhase.SMOKE)
    )

    assert registration.schema_version == "0.2"
    assert registration.id == "t16-live-llm-preregistration-v2"
    assert matrix.schema_version == "0.2"
    assert matrix.id == "t16-smoke-v2"
    assert set(scenarios) == {item.condition_id for item in registration.conditions}


def test_live_phase_rejects_binding_drift_before_any_provider_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = CompletingClient()

    def reject_bindings(*_args: object) -> dict[str, object]:
        raise PreregistrationBindingError("drifted-condition", "测试契约漂移")

    monkeypatch.setattr(live_run, "verify_scenario_bindings", reject_bindings, raising=False)

    with pytest.raises(PreregistrationBindingError, match="测试契约漂移"):
        execute_live_phase(
            LivePhaseRequest(ROOT, Path("unused-binding-drift-output"), LivePhase.SMOKE),
            client,
        )

    assert client.calls == 0


def test_smoke_phase_schedules_48_unique_trials_and_resume_skips_them(tmp_path: Path) -> None:
    output_root = tmp_path / "smoke"
    client = CompletingClient()
    request = LivePhaseRequest(
        project_root=ROOT,
        output_root=output_root,
        phase=LivePhase.SMOKE,
    )

    summary = execute_live_phase(request, client)

    assert summary.expected_trial_count == 48
    assert summary.completed_trial_count == 48
    assert summary.new_trial_count == 48
    assert summary.unique_trial_id_count == 48
    assert summary.stopped is False
    assert summary.live_gate_passed is True
    assert summary.actual_estimated_cost_usd > Decimal(0)
    assert summary.conservative_reserved_usd <= Decimal("0.50")
    # 48 条链中 8 条 M2 各执行四个 Session，其余条件各执行一次。
    assert client.calls == 72
    records = LiveResultStore(output_root / "trial-results.jsonl").read_records()
    assert len(records) == 48

    resumed = execute_live_phase(
        LivePhaseRequest(
            project_root=ROOT,
            output_root=output_root,
            phase=LivePhase.SMOKE,
            resume=True,
        ),
        client,
    )

    assert resumed.completed_trial_count == 48
    assert resumed.new_trial_count == 0
    assert client.calls == 72


def test_gateway_crash_stops_and_preserves_completed_trials(tmp_path: Path) -> None:
    output_root = tmp_path / "crash"

    summary = execute_live_phase(
        LivePhaseRequest(
            project_root=ROOT,
            output_root=output_root,
            phase=LivePhase.SMOKE,
        ),
        CompletingClient(crash_on_call=3),
    )

    assert summary.stopped is True
    assert summary.stop_reason is LiveStopReason.GATEWAY_CRASH
    assert summary.completed_trial_count == 2
    assert summary.new_trial_count == 2
    assert summary.conservative_reserved_usd > summary.actual_estimated_cost_usd
    records = LiveResultStore(output_root / "trial-results.jsonl").read_records()
    assert len(records) == 2


def test_infrastructure_failure_stops_after_one_trial_and_resume_does_not_spend_more(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "timeout"
    failing = CompletingClient(fail_with_timeout=True)
    request = LivePhaseRequest(ROOT, output_root, LivePhase.SMOKE)

    summary = execute_live_phase(request, failing)

    assert summary.stop_reason is LiveStopReason.INFRASTRUCTURE_FAILURE
    assert summary.failure_counts.timeout == 1
    assert summary.completed_trial_count == 1
    assert failing.calls == 2
    healthy = CompletingClient()
    resumed = execute_live_phase(
        LivePhaseRequest(ROOT, output_root, LivePhase.SMOKE, resume=True),
        healthy,
    )
    assert resumed.stop_reason is LiveStopReason.INFRASTRUCTURE_FAILURE
    assert healthy.calls == 0


def test_provider_failure_summary_includes_only_safe_http_status(tmp_path: Path) -> None:
    summary = execute_live_phase(
        LivePhaseRequest(ROOT, tmp_path / "provider", LivePhase.SMOKE),
        CompletingClient(fail_with_provider_status=404),
    )

    assert summary.stop_reason is LiveStopReason.INFRASTRUCTURE_FAILURE
    assert summary.stop_detail == (
        "provider_error:status=404:type=invalid_request_error:"
        "code=unsupported_parameter:param=temperature"
    )


def test_model1_records_schema_invalid_trial_and_continues_matrix(tmp_path: Path) -> None:
    summary = execute_live_phase(
        LivePhaseRequest(ROOT, tmp_path / "model1", LivePhase.MODEL1),
        CompletingClient(schema_reject_on_call=1),
    )

    assert summary.completed_trial_count == 360
    assert summary.failure_counts.schema_rejection == 1
    assert summary.result_counts.invalid >= 1
    assert summary.stopped is False
    assert summary.live_gate_passed is True


def test_model1_records_exhausted_transient_timeout_and_continues(tmp_path: Path) -> None:
    summary = execute_live_phase(
        LivePhaseRequest(ROOT, tmp_path / "model1-timeout", LivePhase.MODEL1),
        CompletingClient(timeout_calls=(1, 2)),
    )

    assert summary.completed_trial_count == 360
    assert summary.failure_counts.timeout == 1
    assert summary.stopped is False
    assert summary.live_gate_passed is True


def test_smoke_budget_is_checked_before_client_and_preserves_empty_store(tmp_path: Path) -> None:
    output_root = tmp_path / "budget"
    client = CompletingClient()

    summary = execute_live_phase(
        LivePhaseRequest(
            ROOT,
            output_root,
            LivePhase.SMOKE,
            initial_total_reserved_usd=Decimal("0.4999"),
        ),
        client,
    )

    assert summary.stop_reason is LiveStopReason.BUDGET_LIMIT
    assert summary.stop_detail == "total_cost"
    assert summary.completed_trial_count == 0
    assert summary.conservative_reserved_usd == Decimal("0.4999")
    assert client.calls == 0
    assert LiveResultStore(output_root / "trial-results.jsonl").read_records() == ()


def _seed_partial_live_phase(tmp_path: Path, *, crash_on_call: int = 2) -> Path:
    output_root = tmp_path / "resume-contract"
    seed_client = CompletingClient(crash_on_call=crash_on_call)
    summary = execute_live_phase(
        LivePhaseRequest(ROOT, output_root, LivePhase.SMOKE),
        seed_client,
    )
    assert summary.stop_reason is LiveStopReason.GATEWAY_CRASH
    assert summary.completed_trial_count == crash_on_call - 1
    return output_root


def _resume_without_calls(output_root: Path, match: str) -> None:
    client = CompletingClient()
    with pytest.raises(RuntimeError, match=match):
        execute_live_phase(
            LivePhaseRequest(ROOT, output_root, LivePhase.SMOKE, resume=True),
            client,
        )
    assert client.calls == 0


def test_resume_rejects_recompiled_prompt_drift_before_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = _seed_partial_live_phase(tmp_path)
    original = live_run.build_live_trial_design

    def drift_prompt(*args: object, **kwargs: object) -> LiveTrialDesign:
        design = original(*args, **kwargs)
        first = design.sessions[0]
        drifted = first.model_copy(
            update={
                "input_items": (
                    *first.input_items,
                    {"role": "user", "content": "resume prompt drift"},
                )
            }
        )
        return design.model_copy(update={"sessions": (drifted, *design.sessions[1:])})

    monkeypatch.setattr(live_run, "build_live_trial_design", drift_prompt)

    _resume_without_calls(output_root, "model_input_sha256")


def test_resume_rejects_live_config_drift_before_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = _seed_partial_live_phase(tmp_path)
    original = live_run.load_t16c_config

    def drift_config(path: Path) -> T16CLiveConfig:
        config = original(path)
        return config.model_copy(update={"max_smoke_attempts": 2})

    monkeypatch.setattr(live_run, "load_t16c_config", drift_config)

    _resume_without_calls(output_root, "phase_contract_sha256")


def test_resume_rejects_persisted_phase_contract_drift_before_client(tmp_path: Path) -> None:
    output_root = _seed_partial_live_phase(tmp_path)
    contract_path = output_root / "phase-contract.json"
    payload = json.loads(contract_path.read_text(encoding="utf-8"))
    payload["phase_contract_sha256"] = "0" * 64
    contract_path.write_text(json.dumps(payload), encoding="utf-8")

    _resume_without_calls(output_root, "phase_contract_sha256")


def test_resume_rejects_record_outside_current_matrix_before_client(tmp_path: Path) -> None:
    output_root = _seed_partial_live_phase(tmp_path)
    result_path = output_root / "trial-results.jsonl"
    payload = json.loads(result_path.read_text(encoding="utf-8").splitlines()[0])
    payload["matrix_trial_id"] = "outside-current-matrix"
    payload["result"]["trial_id"] = "live--outside-current-matrix"
    with result_path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(payload))
        stream.write("\n")

    _resume_without_calls(output_root, "current Matrix")


@pytest.mark.parametrize(
    ("drift_kind", "match"),
    [
        ("legacy", "schema_version"),
        ("identity", "semantic_instance_id"),
        ("record_contract", "phase_contract_sha256"),
        ("provider_kind", "provider"),
        ("provider", "model_id"),
        ("temperature", "temperature"),
        ("reasoning", "reasoning_effort"),
        ("max_turns", "max_agent_turns"),
        ("aliases", "expected_target_effect_aliases"),
    ],
)
def test_resume_rejects_each_existing_record_contract_drift_before_client(
    tmp_path: Path,
    drift_kind: str,
    match: str,
) -> None:
    output_root = _seed_partial_live_phase(tmp_path)
    result_path = output_root / "trial-results.jsonl"
    payload = json.loads(result_path.read_text(encoding="utf-8").splitlines()[0])
    if drift_kind == "legacy":
        payload["schema_version"] = "0.1"
        payload.pop("phase_contract_sha256")
    elif drift_kind == "identity":
        payload["result"]["semantic_instance_id"] = "drifted-instance"
    elif drift_kind == "record_contract":
        payload["phase_contract_sha256"] = "0" * 64
    elif drift_kind == "provider_kind":
        payload["result"]["provider"] = "fake"
    elif drift_kind == "provider":
        payload["result"]["model_id"] = "drifted-model"
    elif drift_kind == "temperature":
        payload["result"]["temperature"] = 0.0
    elif drift_kind == "reasoning":
        payload["result"]["reasoning_effort"] = "low"
    elif drift_kind == "max_turns":
        payload["result"]["max_agent_turns"] = 11
    else:
        payload["expected_target_effect_aliases"] = ["drifted-selector"]
        for session in payload["sessions"]:
            session["expected_target_effect_aliases"] = ["drifted-selector"]
    result_path.write_text(f"{json.dumps(payload)}\n", encoding="utf-8")

    _resume_without_calls(output_root, match)


def test_resume_rejects_missing_schema_version_before_client(tmp_path: Path) -> None:
    output_root = _seed_partial_live_phase(tmp_path)
    result_path = output_root / "trial-results.jsonl"
    payload = json.loads(result_path.read_text(encoding="utf-8").splitlines()[0])
    payload.pop("schema_version")
    result_path.write_text(f"{json.dumps(payload)}\n", encoding="utf-8")
    client = CompletingClient()

    with pytest.raises(ValidationError):
        execute_live_phase(
            LivePhaseRequest(ROOT, output_root, LivePhase.SMOKE, resume=True),
            client,
        )

    assert client.calls == 0


def test_resume_rejects_mixed_actual_model_revisions_before_client(tmp_path: Path) -> None:
    output_root = _seed_partial_live_phase(tmp_path, crash_on_call=3)
    result_path = output_root / "trial-results.jsonl"
    lines = result_path.read_text(encoding="utf-8").splitlines()
    second = json.loads(lines[1])
    second["result"]["model_revision"] = "gpt-5.6-luna-drifted"
    result_path.write_text(f"{lines[0]}\n{json.dumps(second)}\n", encoding="utf-8")

    _resume_without_calls(output_root, "model_revision")


def test_resume_contract_changes_when_execution_source_hash_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = _seed_partial_live_phase(tmp_path)
    monkeypatch.setattr(
        live_phase_contract,
        "_execution_source_hashes",
        lambda _root: {"live_run.py": "f" * 64},
    )

    _resume_without_calls(output_root, "phase_contract_sha256")


def test_new_records_persist_the_phase_contract_hash(tmp_path: Path) -> None:
    output_root = _seed_partial_live_phase(tmp_path)
    contract = json.loads((output_root / "phase-contract.json").read_text(encoding="utf-8"))
    records = LiveResultStore(output_root / "trial-results.jsonl").read_records()

    assert records
    assert all(item.phase_contract_sha256 == contract["phase_contract_sha256"] for item in records)


def test_model_revision_switch_stops_after_preserving_second_trial_and_budget(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "revision-switch"
    client = CompletingClient(
        model_revisions=("gpt-5.6-luna-r1", "gpt-5.6-luna-r2", "must-not-run")
    )

    summary = execute_live_phase(
        LivePhaseRequest(ROOT, output_root, LivePhase.SMOKE),
        client,
    )

    assert client.calls == 2
    assert summary.completed_trial_count == 2
    assert summary.new_trial_count == 2
    assert summary.stop_reason is LiveStopReason.CONTRACT_MISMATCH
    assert summary.stop_detail == "model_revision_changed"
    assert summary.live_gate_passed is False
    records = LiveResultStore(output_root / "trial-results.jsonl").read_records()
    assert tuple(item.result.model_revision for item in records) == (
        "gpt-5.6-luna-r1",
        "gpt-5.6-luna-r2",
    )
    assert len((output_root / "budget-journal.jsonl").read_text(encoding="utf-8").splitlines()) == 2

    _resume_without_calls(output_root, "model_revision")


def test_failed_call_revision_fallback_is_not_misclassified_as_contract_drift(
    tmp_path: Path,
) -> None:
    client = CompletingClient(
        timeout_calls=(2, 3),
        model_revisions=("gpt-5.6-luna-r1",),
    )

    summary = execute_live_phase(
        LivePhaseRequest(ROOT, tmp_path / "revision-timeout", LivePhase.SMOKE),
        client,
    )

    assert client.calls == 3
    assert summary.completed_trial_count == 2
    assert summary.stop_reason is LiveStopReason.INFRASTRUCTURE_FAILURE
    assert summary.stop_detail == "timeout"
