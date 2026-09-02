from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from skillflow.experiment.t16.provider import TokenUsage
from skillflow.experiment.t17.budget_proposal import (
    T17BudgetProposal,
    build_followup_budget_proposal,
    build_initial_budget_proposal,
)
from skillflow.experiment.t17.live_attempt_models import (
    T17LiveFailureKind,
    T17LiveTerminalStatus,
    T17LiveUnitKind,
    T17LiveUnitRecord,
)
from skillflow.experiment.t17.live_matrix import (
    T17LiveStage,
    load_live_matrix,
)
from skillflow.experiment.t17.live_reference_client import ReferenceLiveTelemetry
from skillflow.experiment.t17.live_result_store import T17LiveResultStore


def test_initial_luna_budget_proposal_is_zero_call_and_conservatively_bounded() -> None:
    # Given: the completed historical Luna Canary and the new 24+18 T17-E Matrix.
    matrix = load_live_matrix(Path("experiments/t17/matrix_canary.yaml"))

    # When: the offline proposal is built before any T17 API request.
    proposal = build_initial_budget_proposal(
        Path("runs/t16d2-v31-canary-live-20260830-01/attempt-01/run-summary.json"),
        matrix,
    )

    # Then: it requests a bounded approval without claiming statistical p95 or spending.
    assert proposal.api_calls_made == 0
    assert proposal.authorization_status == "pending_user_approval"
    assert (proposal.scheduled_core_trials, proposal.scheduled_replay_pairs) == (24, 18)
    assert proposal.projected_actual_usd > Decimal("0.06")
    assert proposal.conservative_projected_usd > proposal.projected_actual_usd
    assert proposal.requested_max_total_usd == Decimal("0.25")
    assert proposal.projection_kind == "engineering_upper_bound_not_statistical_p95"


def test_retry_budget_proposal_cannot_exceed_campaign_total() -> None:
    matrix = load_live_matrix(Path("experiments/t17/matrix_canary.yaml"))
    proposal = build_initial_budget_proposal(
        Path("runs/t16d2-v31-canary-live-20260830-01/attempt-01/run-summary.json"),
        matrix,
    )
    values = proposal.model_dump()
    values.update(
        campaign_max_total_usd=Decimal("0.25"),
        prior_attempt_conservative_reserved_usd=Decimal("0.0009499"),
        requested_max_total_usd=Decimal("0.2490502"),
    )

    with pytest.raises(ValidationError, match="Campaign"):
        T17BudgetProposal.model_validate(values)


def test_retry_budget_proposal_rejects_actual_cost_above_reservation() -> None:
    matrix = load_live_matrix(Path("experiments/t17/matrix_canary.yaml"))
    proposal = build_initial_budget_proposal(
        Path("runs/t16d2-v31-canary-live-20260830-01/attempt-01/run-summary.json"),
        matrix,
    )
    values = proposal.model_dump()
    values.update(
        prior_attempt_actual_estimated_usd=Decimal("0.02"),
        prior_attempt_conservative_reserved_usd=Decimal("0.01"),
    )

    with pytest.raises(ValidationError, match="actual cost"):
        T17BudgetProposal.model_validate(values)


def test_followup_budget_proposal_uses_observed_unit_p95_and_target_prices(
    tmp_path: Path,
) -> None:
    # Given: three terminal units with actual usage from a completed prior stage.
    attempt = tmp_path / "canary" / "attempt-01"
    attempt.mkdir(parents=True)
    store = T17LiveResultStore(attempt / "trial-results.jsonl")
    store.open_new()
    for sequence, input_tokens in enumerate((100, 200, 300), start=1):
        store.append(
            T17LiveUnitRecord(
                sequence=sequence,
                stage=T17LiveStage.CANARY,
                unit_id=f"unit-{sequence}",
                trial_id=f"trial-{sequence}",
                unit_kind=T17LiveUnitKind.CORE,
                variant="b0-monitor",
                source_variant="b0-monitor",
                enforcement_mode="monitor",
                scenario_id="B0",
                semantic_instance_id=f"b0-monitor-s0{sequence}",
                semantic_template_id=f"s0{sequence}",
                repeat_index=1,
                terminal_status=T17LiveTerminalStatus.INCOMPLETE,
                failure_kind=T17LiveFailureKind.INFRASTRUCTURE,
                failure_detail="test_fixture",
                telemetry=ReferenceLiveTelemetry(
                    api_call_count=1,
                    response_count=1,
                    agent_step_count=1,
                    retry_count=0,
                    refusal_count=0,
                    no_call_count=0,
                    token_usage=TokenUsage(
                        input_tokens=input_tokens,
                        cached_input_tokens=0,
                        output_tokens=20,
                        reasoning_tokens=10,
                    ),
                    latency_ms=10,
                    estimated_cost_usd=Decimal("0.001"),
                    conservative_reserved_usd=Decimal("0.002"),
                ),
                run_ids=(),
                replay_ids=(),
                task_success=None,
                safe_task_success=None,
                evidence_ids=(),
                artifacts=(),
            )
        )
    (attempt / "live-summary.json").write_text("{}\n", encoding="utf-8")
    target = load_live_matrix(Path("experiments/t17/matrix_model1.yaml"))

    # When: the next-stage proposal is generated without an API call.
    proposal = build_followup_budget_proposal(attempt, target)

    # Then: target pricing, observed p95 and bounded hard gates are explicit.
    assert proposal.api_calls_made == 0
    assert proposal.historical_source_kind == "t17_live_stage"
    assert proposal.projection_kind == "observed_unit_p95_repriced"
    assert proposal.historical_unit_cost_p95_usd is not None
    assert proposal.projected_p95_total_usd == proposal.conservative_projected_usd
    assert proposal.requested_max_total_usd <= target.budget.max_total_usd
    assert proposal.requested_max_cost_per_run_usd <= target.budget.max_cost_per_run_usd
