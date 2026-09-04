"""在申请密钥或建立网络客户端之前核对完整离线证据和明确金额批准。"""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from skillflow.experiment.t17.minimal.artifacts import write_checked_json
from skillflow.experiment.t17.v2.campaign_models import CampaignClaim
from skillflow.experiment.t17.v2.canonical import canonical_digest, model_digest
from skillflow.experiment.t17.v2.config_models import V2Configuration, V2Matrix
from skillflow.experiment.t17.v2.cost_history import historical_usage
from skillflow.experiment.t17.v2.cost_models import BudgetApproval, CostPlan
from skillflow.experiment.t17.v2.cost_plan import stage_cost
from skillflow.experiment.t17.v2.formal_scope import require_full_t17
from skillflow.experiment.t17.v2.frozen import file_digest, inside, verify_files
from skillflow.experiment.t17.v2.loading import read_model
from skillflow.experiment.t17.v2.readiness import offline_evidence
from skillflow.experiment.t17.v2.run_models import PhaseContract
from skillflow.experiment.t17.v2.static_protocol import verify_protocol


@dataclass(frozen=True, slots=True)
class CampaignSetup:
    """全部路径必须位于项目内，新输出不得已存在。"""

    root: Path
    output: Path
    protocol: Path
    cost_plan: Path
    approval: Path


@dataclass(frozen=True, slots=True)
class PreparedCampaign:
    """准备期间没有真实调用，执行只消费这些已验证对象。"""

    setup: CampaignSetup
    configuration: V2Configuration
    matrices: tuple[V2Matrix, ...]
    plan: CostPlan
    approval: BudgetApproval
    plan_sha256: str
    approval_sha256: str
    phases: tuple[PhaseContract, ...]


def prepare_campaign(setup: CampaignSetup) -> PreparedCampaign:
    """拒绝缺批准、金额不符、改动矩阵、漂移代码或失效离线证据。"""
    root = setup.root.resolve()
    for path in (setup.output, setup.protocol, setup.cost_plan, setup.approval):
        inside(root, path.resolve().relative_to(root).as_posix())
    if setup.output.exists():
        raise ValueError("v2_campaign_output_already_exists")
    plan = read_model(setup.cost_plan, CostPlan)
    approval = read_model(setup.approval, BudgetApproval)
    digest = file_digest(setup.cost_plan).sha256
    if (
        approval.cost_plan_sha256 != digest
        or approval.approved_max_total_usd != plan.requested_max_total_usd
    ):
        raise ValueError("v2_total_budget_not_explicitly_approved")
    if (
        inside(root, plan.protocol_relative_path) != setup.protocol.resolve()
        or file_digest(setup.protocol / "protocol-manifest.json") != plan.protocol_manifest
    ):
        raise ValueError("v2_cost_plan_protocol_binding")
    config, matrices = verify_protocol(root, setup.protocol)
    require_full_t17(root, config, matrices)
    if config.protocol_id != plan.protocol_id or model_digest(config) != plan.configuration_sha256:
        raise ValueError("v2_cost_plan_configuration_binding")
    verify_files(root, plan.offline_evidence)
    evidence = offline_evidence(
        root, inside(root, plan.offline_relative_path), model_digest(config)
    )
    if evidence != plan.offline_evidence:
        raise ValueError("v2_cost_plan_readiness_binding")
    history, samples = historical_usage(root, inside(root, plan.historical.source_path))
    if (
        history != plan.historical
        or tuple(
            stage_cost(root, matrix, planned.budget, samples)
            for matrix, planned in zip(matrices, plan.stages, strict=True)
        )
        != plan.stages
    ):
        raise ValueError("v2_cost_plan_projection_drift")
    prepared = PreparedCampaign(
        setup,
        config,
        matrices,
        plan,
        approval,
        digest,
        file_digest(setup.approval).sha256,
        tuple(
            read_model(setup.protocol / ("phase-" + m.stage.value + ".json"), PhaseContract)
            for m in matrices
        ),
    )
    if claim_path(prepared).exists():
        raise ValueError("v2_budget_approval_already_used_keep_partial")
    return prepared


def claim_path(prepared: PreparedCampaign) -> Path:
    """稳定批准 ID 防止仅复制或重格式化文件后再次消费同一预算。"""
    name = canonical_digest(prepared.approval.approval_id)
    return prepared.setup.root / "runs" / "t17-v2-budget-claims" / (name + ".json")


def claim_campaign(prepared: PreparedCampaign) -> CampaignClaim:
    """独占保存批准的使用记录；失败不删除，也不续填旧尝试。"""
    claim = CampaignClaim(
        approval_id=prepared.approval.approval_id,
        approval_sha256=prepared.approval_sha256,
        cost_plan_sha256=prepared.plan_sha256,
        approved_total_usd=prepared.approval.approved_max_total_usd,
        output_relative_path=prepared.setup.output.resolve()
        .relative_to(prepared.setup.root.resolve())
        .as_posix(),
        started_at=datetime.now(UTC),
    )
    path = claim_path(prepared)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_checked_json(path, claim)
    return claim
