import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from skillflow.experiment.io import write_json_model
from skillflow.experiment.t16.openai_response_models import OpenAIResponsesCall
from skillflow.experiment.t16.openai_responses import OpenAIResponsesTurn
from skillflow.experiment.t16.provider import TokenUsage
from skillflow.experiment.t17.budget_proposal import T17BudgetProposal
from skillflow.experiment.t17.live_journal_models import T17LiveJournalError
from skillflow.experiment.t17.live_matrix import (
    load_live_matrix,
    load_live_preregistration,
)
from skillflow.experiment.t17.live_preflight import (
    T17LivePreflightError,
    T17LivePreflightPaths,
    build_approved_live_config,
    build_budget_approval,
    build_live_preflight,
)
from skillflow.experiment.t17.live_reference_client import (
    OpenAIReferenceModelClient,
)
from skillflow.experiment.t17.live_result_store import load_live_unit_records
from skillflow.experiment.t17.live_stage import (
    T17LiveStageRequest,
    execute_live_stage,
)
from skillflow.experiment.t17.phase_integrity import T17PhaseIntegrityError
from skillflow.experiment.t17.phase_report import (
    T17PhaseReportRequest,
    build_phase_metrics_report,
    write_phase_metrics_report,
)

ROOT = Path.cwd()
PROPOSAL_PATH = ROOT / "docs/evidence/t17-e-budget-proposal.json"


class RegisteredActionClient:
    """从请求中的封闭动作目录选择全部动作，不进行网络 I/O。"""

    def __init__(self) -> None:
        self.call_count = 0

    def create(self, call: OpenAIResponsesCall) -> OpenAIResponsesTurn:
        self.call_count += 1
        user_item = call.input_items[-1]
        content = user_item["content"]
        assert isinstance(content, list)
        block = content[0]
        assert isinstance(block, dict)
        contract = json.loads(str(block["text"]))
        output = json.dumps(
            {
                "selected_action_ids": contract["allowed_action_ids"],
                "output_text": contract["installed_skill_expected_output"],
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return OpenAIResponsesTurn(
            response_id=f"fake-response-{self.call_count}",
            model_revision=call.model,
            status="completed",
            function_calls=(),
            continuation_items=(),
            output_text=output,
            refusal=False,
            token_usage=TokenUsage(
                input_tokens=10,
                cached_input_tokens=0,
                output_tokens=2,
                reasoning_tokens=1,
            ),
            latency_ms=2,
        )


def test_t17_live_fake_stage_closes_24_core_and_18_replays(
    tmp_path: Path,
) -> None:
    # Given: a separately approved, immutable Canary attempt with a fake transport.
    matrix_path = ROOT / "experiments/t17/matrix_canary.yaml"
    preregistration_path = ROOT / "experiments/t17/preregistration.yaml"
    registry_path = ROOT / "experiments/t17/scenario_measurements.yaml"
    base_matrix_path = ROOT / "scenarios/matrix/mvp.yaml"
    proposal = T17BudgetProposal.model_validate_json(PROPOSAL_PATH.read_text(encoding="utf-8"))
    matrix = load_live_matrix(matrix_path)
    registration = load_live_preregistration(preregistration_path)
    attempt = tmp_path / "attempt-01"
    attempt.mkdir()
    approval = build_budget_approval(
        PROPOSAL_PATH,
        proposal,
        datetime.now(UTC),
        Decimal("0.25"),
        Decimal("0.05"),
    )
    approval_path = attempt / "budget-approval.json"
    write_json_model(approval_path, approval)
    config = build_approved_live_config(
        registration,
        matrix,
        proposal,
        approval,
    )
    preflight_inputs = T17LivePreflightPaths(
        project_root=ROOT,
        preregistration_path=preregistration_path,
        matrix_path=matrix_path,
        registry_path=registry_path,
        base_matrix_path=base_matrix_path,
        proposal_path=PROPOSAL_PATH,
        approval_path=approval_path,
    )
    preflight = build_live_preflight(
        preflight_inputs,
        config,
        datetime.now(UTC),
    )
    preflight_path = attempt / "preflight.json"
    write_json_model(preflight_path, preflight)
    transport = RegisteredActionClient()

    # When: the live stage is executed through the real Reference Harness path.
    result = execute_live_stage(
        T17LiveStageRequest(
            project_root=ROOT,
            attempt_root=attempt,
            matrix_path=matrix_path,
            base_matrix_path=base_matrix_path,
            registry_path=registry_path,
            preflight_path=preflight_path,
            preflight_inputs=preflight_inputs,
            config=config,
        ),
        OpenAIReferenceModelClient(config, transport),
    )

    # Then: every scheduled unit has trusted evidence and no response body is logged.
    assert result.summary.live_gate_passed is True
    assert result.summary.completed_core_trials == 24
    assert result.summary.completed_replay_pairs == 18
    assert len(load_live_unit_records(attempt / "trial-results.jsonl")) == 42
    usage_raw = (attempt / "actual-usage-journal.jsonl").read_text(encoding="utf-8")
    assert "selected_action_ids" not in usage_raw
    assert "installed_skill_expected_output" not in usage_raw

    # And: the report command closes all metric groups from the Raw hashes.
    report_request = T17PhaseReportRequest(
        attempt_root=attempt,
        matrix_path=matrix_path,
        registry_path=registry_path,
        base_matrix_path=base_matrix_path,
        output_path=attempt / "phase-metrics.json",
    )
    metrics = write_phase_metrics_report(report_request)
    assert metrics.standard_risk_scope == "scheduled_complete"
    assert metrics.required_metrics_complete is True
    assert metrics.task_success_rate.numerator == 20
    assert metrics.task_success_rate.denominator == 24
    assert metrics.safe_task_success_rate.numerator == 11
    assert metrics.uea.uea_count == 8
    assert metrics.provenance.status.value == "measured"
    assert len(metrics.standard_risk_report.hiaa_designs) == 2
    assert all(
        interval.status.value == "not_applicable"
        for interval in metrics.bootstrap_intervals.values()
    )
    assert metrics.efficiency.telemetry.agent_step_count > 0
    assert metrics.efficiency.telemetry.retry_count == 0

    _assert_phase_tampering_blocked(attempt, report_request)


def _assert_phase_tampering_blocked(
    attempt: Path,
    report_request: T17PhaseReportRequest,
) -> None:
    """Journal chain or Raw task tampering blocks metric completion."""
    journal_path = attempt / "actual-usage-journal.jsonl"
    journal_raw = journal_path.read_text(encoding="utf-8")
    journal_path.write_text(
        journal_raw.replace('"api_call_count":1', '"api_call_count":2', 1),
        encoding="utf-8",
    )
    with pytest.raises(T17LiveJournalError):
        build_phase_metrics_report(report_request)
    journal_path.write_text(journal_raw, encoding="utf-8")

    results_path = attempt / "trial-results.jsonl"
    results_raw = results_path.read_text(encoding="utf-8")
    results_path.write_text(
        results_raw.replace('"task_success":true', '"task_success":false', 1),
        encoding="utf-8",
    )
    with pytest.raises(T17PhaseIntegrityError):
        build_phase_metrics_report(report_request)
    results_path.write_text(results_raw, encoding="utf-8")


def test_live_stage_revalidates_preflight_before_client(
    tmp_path: Path,
) -> None:
    # Given: a valid preflight whose confirmed proposal changes afterwards.
    matrix_path = ROOT / "experiments/t17/matrix_canary.yaml"
    preregistration_path = ROOT / "experiments/t17/preregistration.yaml"
    registry_path = ROOT / "experiments/t17/scenario_measurements.yaml"
    base_matrix_path = ROOT / "scenarios/matrix/mvp.yaml"
    proposal_path = tmp_path / "proposal.json"
    proposal_path.write_bytes(PROPOSAL_PATH.read_bytes())
    proposal = T17BudgetProposal.model_validate_json(proposal_path.read_text(encoding="utf-8"))
    matrix = load_live_matrix(matrix_path)
    registration = load_live_preregistration(preregistration_path)
    attempt = tmp_path / "drift-attempt"
    attempt.mkdir()
    approval = build_budget_approval(
        proposal_path,
        proposal,
        datetime.now(UTC),
        Decimal("0.25"),
        Decimal("0.05"),
    )
    approval_path = attempt / "budget-approval.json"
    write_json_model(approval_path, approval)
    config = build_approved_live_config(
        registration,
        matrix,
        proposal,
        approval,
    )
    preflight_inputs = T17LivePreflightPaths(
        project_root=ROOT,
        preregistration_path=preregistration_path,
        matrix_path=matrix_path,
        registry_path=registry_path,
        base_matrix_path=base_matrix_path,
        proposal_path=proposal_path,
        approval_path=approval_path,
    )
    preflight = build_live_preflight(
        preflight_inputs,
        config,
        datetime.now(UTC),
    )
    preflight_path = attempt / "preflight.json"
    write_json_model(preflight_path, preflight)
    proposal_path.write_bytes(proposal_path.read_bytes() + b"\n")
    transport = RegisteredActionClient()

    # When/Then: execution stops before Raw creation or any provider call.
    with pytest.raises(T17LivePreflightError):
        execute_live_stage(
            T17LiveStageRequest(
                project_root=ROOT,
                attempt_root=attempt,
                matrix_path=matrix_path,
                base_matrix_path=base_matrix_path,
                registry_path=registry_path,
                preflight_path=preflight_path,
                preflight_inputs=preflight_inputs,
                config=config,
            ),
            OpenAIReferenceModelClient(config, transport),
        )
    assert transport.call_count == 0
    assert not (attempt / "raw").exists()
    assert not (attempt / "actual-usage-journal.jsonl").exists()
