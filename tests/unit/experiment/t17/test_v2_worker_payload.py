"""真实进程任务格式往返；合成批准只用于内存测试，不授权 API。"""

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from tests.unit.experiment.t17.v2_test_history import write_history

from skillflow.experiment.t17.live_matrix import T17LiveStage, load_live_preregistration
from skillflow.experiment.t17.v2.campaign_setup import CampaignSetup, PreparedCampaign
from skillflow.experiment.t17.v2.canonical import model_digest
from skillflow.experiment.t17.v2.configuration import build_configuration, write_configuration
from skillflow.experiment.t17.v2.cost_history import historical_usage
from skillflow.experiment.t17.v2.cost_models import BudgetApproval, CostPlan
from skillflow.experiment.t17.v2.cost_plan import stage_cost
from skillflow.experiment.t17.v2.frozen import FrozenFile
from skillflow.experiment.t17.v2.matrix import build_matrix
from skillflow.experiment.t17.v2.stage_contract import freeze_phase
from skillflow.experiment.t17.v2.worker_models import StageJob


def test_full_campaign_pipe_round_trip(t17_cli_root: Path) -> None:
    root, directory = Path.cwd(), t17_cli_root / "pipe-configuration"
    config, bundles = build_configuration(root, directory)
    write_configuration(root, directory, config, bundles)
    matrices = tuple(build_matrix(root, config, stage) for stage in T17LiveStage)
    phases = tuple(freeze_phase(root, config, m, "live_reference") for m in matrices)
    old = load_live_preregistration(root / "experiments/t17/preregistration.yaml")
    budgets = (
        old.model1_budget,
        old.model1_full_budget,
        old.model2_budget,
        old.model2_full_budget,
        old.defense_budget,
    )
    history_path = t17_cli_root / "synthetic-history.jsonl"
    write_history(history_path)
    history, samples = historical_usage(root, history_path)
    costs = tuple(stage_cost(root, m, b, samples) for m, b in zip(matrices, budgets, strict=True))
    total = sum((b.max_total_usd for b in budgets), Decimal(0))
    plan = CostPlan(
        protocol_id=config.protocol_id,
        protocol_relative_path=directory.relative_to(root).as_posix(),
        configuration_sha256=model_digest(config),
        protocol_manifest=FrozenFile(sha256="a" * 64, size_bytes=0),
        created_at=datetime(2026, 9, 4, tzinfo=UTC),
        historical=history,
        offline_evidence={},
        offline_relative_path="synthetic-not-executed",
        stages=costs,
        requested_max_total_usd=total,
        remaining_requested_usd=total,
    )
    approval = BudgetApproval(
        approval_id="synthetic-in-memory-no-real-authorization",
        cost_plan_sha256="b" * 64,
        approved_at=datetime(2026, 9, 4, tzinfo=UTC),
        approved_max_total_usd=total,
        user_explicit_approval=True,
        approval_basis="software_test_only_never_written_or_used_for_api",
    )
    setup = CampaignSetup(root, t17_cli_root / "unused-output", directory, directory, directory)
    prepared = PreparedCampaign(setup, config, matrices, plan, approval, "b" * 64, "c" * 64, phases)
    job = StageJob(prepared=prepared, index=0, attempt_number=1, approved_phase=phases[0])
    encoded = job.model_dump_json().encode("utf-8")
    assert len(encoded) < 64 * 1024 * 1024
    assert StageJob.model_validate_json(encoded) == job
    assert not setup.output.exists()
    with pytest.raises(ValueError, match="v2_worker_approved_phase_binding"):
        StageJob(prepared=prepared, index=0, attempt_number=1, approved_phase=phases[1])
