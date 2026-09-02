from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from skillflow.experiment.io import write_json_model
from skillflow.experiment.t17.budget_proposal import T17BudgetProposal
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
from skillflow.experiment.t17.live_reference_client import T17ApprovedLiveConfig

ROOT = Path()
PROPOSAL_PATH = Path("docs/evidence/t17-e-budget-proposal.json")


def _prepared(
    tmp_path: Path,
) -> tuple[T17LivePreflightPaths, T17ApprovedLiveConfig]:
    proposal = T17BudgetProposal.model_validate_json(PROPOSAL_PATH.read_text(encoding="utf-8"))
    matrix = load_live_matrix(Path("experiments/t17/matrix_canary.yaml"))
    registration = load_live_preregistration(Path("experiments/t17/preregistration.yaml"))
    approval = build_budget_approval(
        PROPOSAL_PATH,
        proposal,
        datetime.now(UTC),
        Decimal("0.25"),
        Decimal("0.05"),
    )
    approval_path = tmp_path / "budget-approval.json"
    write_json_model(approval_path, approval)
    config = build_approved_live_config(
        registration,
        matrix,
        proposal,
        approval,
    )
    paths = T17LivePreflightPaths(
        project_root=ROOT,
        preregistration_path=Path("experiments/t17/preregistration.yaml"),
        matrix_path=Path("experiments/t17/matrix_canary.yaml"),
        registry_path=Path("experiments/t17/scenario_measurements.yaml"),
        base_matrix_path=Path("scenarios/matrix/mvp.yaml"),
        proposal_path=PROPOSAL_PATH,
        approval_path=approval_path,
    )
    return paths, config


def test_live_preflight_rebuilds_canary_before_any_client(
    tmp_path: Path,
) -> None:
    paths, config = _prepared(tmp_path)

    manifest = build_live_preflight(paths, config, datetime.now(UTC))

    assert manifest.scheduled_core_trials == 24
    assert manifest.scheduled_replay_pairs == 18
    assert manifest.provider_model_revision == "gpt-5.6-luna"
    assert manifest.source_hashes
    assert {
        "src/skillflow/experiment/t16/live_agent_calls.py",
        "src/skillflow/experiment/t16/openai_output_schemas.py",
        "src/skillflow/benchmark/harness_factory.py",
        "src/skillflow/adapters/live_reference_harness.py",
    }.issubset(manifest.source_hashes)


def test_live_preflight_rejects_approved_config_drift(
    tmp_path: Path,
) -> None:
    paths, config = _prepared(tmp_path)
    drifted = config.model_copy(
        update={"budget": config.budget.model_copy(update={"max_total_usd": Decimal("0.24")})}
    )

    with pytest.raises(T17LivePreflightError):
        build_live_preflight(paths, drifted, datetime.now(UTC))
