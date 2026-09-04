"""监督控制测试使用冻结输入和合成批准，不消费真实批准或启动网络。"""

from datetime import UTC, datetime
from pathlib import Path

from tests.unit.experiment.t17.v2_test_history import write_history

from skillflow.experiment.t17.live_matrix import T17LiveStage
from skillflow.experiment.t17.minimal.artifacts import write_checked_json
from skillflow.experiment.t17.v2.campaign_models import StageOutcome
from skillflow.experiment.t17.v2.campaign_setup import CampaignSetup, PreparedCampaign
from skillflow.experiment.t17.v2.canonical import model_digest
from skillflow.experiment.t17.v2.config_models import V2Configuration, V2Matrix
from skillflow.experiment.t17.v2.cost_history import historical_usage
from skillflow.experiment.t17.v2.cost_models import BudgetApproval, CostPlan
from skillflow.experiment.t17.v2.frozen import file_digest
from skillflow.experiment.t17.v2.loading import read_model
from skillflow.experiment.t17.v2.run_models import PhaseContract, PhaseGate, UnitUsage
from skillflow.experiment.t17.v2.static_protocol import ProtocolManifest


def prepared_case(directory: Path) -> PreparedCampaign:
    root = Path.cwd()
    source = root / "experiments/t17/v2"
    protocol = directory / "protocol"
    protocol.mkdir(parents=True)
    configuration = read_model(source / "preregistration.json", V2Configuration)
    matrices = tuple(
        read_model(source / f"matrix-{stage.value}.json", V2Matrix) for stage in T17LiveStage
    )
    phases = tuple(
        read_model(source / f"phase-{stage.value}.json", PhaseContract) for stage in T17LiveStage
    )
    for phase in phases:
        write_checked_json(protocol / f"phase-{phase.stage.value}.json", phase)
    write_checked_json(
        protocol / "protocol-manifest.json",
        ProtocolManifest(
            protocol_id=configuration.protocol_id,
            configuration_sha256=model_digest(configuration),
            files={},
        ),
    )
    history_path = directory / "synthetic-history.jsonl"
    write_history(history_path)
    history, _ = historical_usage(root, history_path)
    base = read_model(root / "docs/evidence/t17-v2-cost-plan.json", CostPlan)
    plan = base.model_copy(
        update={
            "protocol_relative_path": protocol.relative_to(root).as_posix(),
            "protocol_manifest": file_digest(protocol / "protocol-manifest.json"),
            "configuration_sha256": model_digest(configuration),
            "historical": history,
            "offline_evidence": {},
            "offline_relative_path": directory.relative_to(root).as_posix() + "/offline",
        }
    )
    plan_path = directory / "synthetic-plan.json"
    write_checked_json(plan_path, plan)
    approval = BudgetApproval(
        approval_id="software-test-only-" + directory.name,
        cost_plan_sha256=file_digest(plan_path).sha256,
        approved_at=datetime(2026, 9, 4, tzinfo=UTC),
        approved_max_total_usd=plan.requested_max_total_usd,
        user_explicit_approval=True,
        approval_basis="unit_control_test_no_network_no_real_authorization",
    )
    approval_path = directory / "synthetic-approval.json"
    write_checked_json(approval_path, approval)
    return PreparedCampaign(
        CampaignSetup(root, directory / "output", protocol, plan_path, approval_path),
        configuration,
        matrices,
        plan,
        approval,
        file_digest(plan_path).sha256,
        file_digest(approval_path).sha256,
        phases,
    )


def control_gate(prepared: PreparedCampaign, index: int, *, passed: bool = True) -> PhaseGate:
    """合成门只测试上层停止控制；不用于任务判定或正式指标期望。"""
    phase = prepared.phases[index]
    return PhaseGate(
        passed=passed,
        scheduled_core=phase.scheduled_core,
        scheduled_replay=phase.scheduled_replay,
        terminal_core=phase.scheduled_core,
        terminal_replay=phase.scheduled_replay,
        completed_core=phase.scheduled_core,
        evaluated_replay=phase.scheduled_replay,
        not_applicable_replay=0,
        infrastructure_invalid=0,
        protocol_errors=0,
        binding_failures=0,
        task_evidence_coverage=1,
        receipt_coverage=1,
        required_hook_coverage=1,
        binding_coverage=1,
        usage_complete=True,
        failures=() if passed else ("synthetic_gate_failure",),
    )


def control_outcome(prepared: PreparedCampaign, index: int, *, passed: bool = True) -> StageOutcome:
    stage = prepared.matrices[index].stage
    return StageOutcome(
        stage=stage,
        status="passed" if passed else "failed",
        reason=None if passed else "worker_exit",
        gate=control_gate(prepared, index, passed=passed),
        raw_relative_path=(prepared.setup.output / stage.value / "attempt-01/raw")
        .relative_to(prepared.setup.root)
        .as_posix(),
        usage=UnitUsage(),
    )
