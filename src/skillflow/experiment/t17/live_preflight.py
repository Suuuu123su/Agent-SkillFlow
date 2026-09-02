"""T17 Live 的预算批准、静态漂移复算与首次调用前预检。"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum, unique
from pathlib import Path
from typing import TypeVar

from skillflow.experiment.io import sha256_file
from skillflow.experiment.t17.budget_proposal import T17BudgetProposal
from skillflow.experiment.t17.live_attempt_models import (
    T17BudgetApproval,
    T17LivePreflightManifest,
)
from skillflow.experiment.t17.live_matrix import (
    T17LiveMatrix,
    T17LivePreregistration,
    T17LiveStage,
    build_live_matrix,
    load_live_matrix,
    load_live_preregistration,
)
from skillflow.experiment.t17.live_reference_client import T17ApprovedLiveConfig
from skillflow.experiment.t17.scenario_registry import (
    load_scenario_measurement_registry,
)
from skillflow.models.matrix import ExperimentMatrix
from skillflow.validation import validate_yaml_document

CanonicalValue = TypeVar("CanonicalValue")
EXPECTED_COUNTS = {
    T17LiveStage.CANARY: (24, 18),
    T17LiveStage.MODEL1: (360, 270),
    T17LiveStage.MODEL2_CANARY: (24, 18),
    T17LiveStage.MODEL2: (360, 270),
    T17LiveStage.DEFENSE: (270, 270),
}


@unique
class T17LivePreflightErrorCode(StrEnum):
    """预算授权与冻结输入的封闭预检失败。"""

    APPROVAL_LIMIT_MISMATCH = "approval_limit_mismatch"
    PROPOSAL_HASH_MISMATCH = "proposal_hash_mismatch"
    CONFIG_DRIFT = "config_drift"
    MATRIX_DRIFT = "matrix_drift"
    COUNT_INVALID = "count_invalid"
    STATIC_LIVE_ENABLED = "static_live_enabled"
    BUDGET_BINDING_INVALID = "budget_binding_invalid"
    TRIAL_BINDING_INVALID = "trial_binding_invalid"
    EXECUTION_DRIFT = "execution_drift"


class T17LivePreflightError(RuntimeError):
    """任何授权或冻结输入漂移都必须先于首次 API 请求失败。"""

    __slots__ = ("code", "identifier")

    def __init__(
        self,
        code: T17LivePreflightErrorCode,
        identifier: str | None = None,
    ) -> None:
        """保存封闭预检码并保留 Exception 运行时状态。"""
        super().__init__(code.value, identifier)
        self.code = code
        self.identifier = identifier

    def __str__(self) -> str:
        """返回不包含密钥、Prompt 或响应的稳定诊断。"""
        suffix = "" if self.identifier is None else f":{self.identifier}"
        return f"{self.code.value}{suffix}"


@dataclass(frozen=True, slots=True)
class T17LivePreflightPaths:
    """构造阶段合同时使用的项目内静态输入。"""

    project_root: Path
    preregistration_path: Path
    matrix_path: Path
    registry_path: Path
    base_matrix_path: Path
    proposal_path: Path
    approval_path: Path


def build_budget_approval(
    proposal_path: Path,
    proposal: T17BudgetProposal,
    approved_at: datetime,
    approved_max_total_usd: Decimal,
    approved_max_cost_per_run_usd: Decimal,
) -> T17BudgetApproval:
    """只接受与提案硬门完全相等的单阶段用户批准。"""
    if (
        approved_max_total_usd != proposal.requested_max_total_usd
        or approved_max_cost_per_run_usd != proposal.requested_max_cost_per_run_usd
    ):
        raise T17LivePreflightError(T17LivePreflightErrorCode.APPROVAL_LIMIT_MISMATCH)
    return T17BudgetApproval(
        stage=proposal.stage,
        approved_at=approved_at,
        proposal_sha256=sha256_file(proposal_path),
        approved_max_total_usd=approved_max_total_usd,
        approved_max_cost_per_run_usd=approved_max_cost_per_run_usd,
    )


def build_approved_live_config(
    registration: T17LivePreregistration,
    matrix: T17LiveMatrix,
    proposal: T17BudgetProposal,
    approval: T17BudgetApproval,
) -> T17ApprovedLiveConfig:
    """从静态关闭配置派生仅当前进程持有的已批准 Live 配置。"""
    _require_budget_binding(matrix, proposal, approval)
    prompt_cache_mode = (
        registration.model1_prompt_cache_mode
        if matrix.stage in {T17LiveStage.CANARY, T17LiveStage.MODEL1}
        else registration.model2_prompt_cache_mode
    )
    return T17ApprovedLiveConfig(
        provider=matrix.provider,
        budget=matrix.budget.model_copy(
            update={
                "allow_live": True,
                "max_total_usd": approval.approved_max_total_usd,
                "max_cost_per_run_usd": (approval.approved_max_cost_per_run_usd),
            }
        ),
        prompt_cache_mode=prompt_cache_mode,
    )


def build_live_preflight(
    paths: T17LivePreflightPaths,
    config: T17ApprovedLiveConfig,
    created_at: datetime,
) -> T17LivePreflightManifest:
    """复算 Matrix、计数、模型、预算和执行源哈希。"""
    root = paths.project_root
    registration = load_live_preregistration(paths.preregistration_path)
    matrix = load_live_matrix(paths.matrix_path)
    registry = load_scenario_measurement_registry(paths.registry_path)
    base_matrix = validate_yaml_document(paths.base_matrix_path, ExperimentMatrix)
    proposal = T17BudgetProposal.model_validate_json(
        paths.proposal_path.read_text(encoding="utf-8")
    )
    approval = T17BudgetApproval.model_validate_json(
        paths.approval_path.read_text(encoding="utf-8")
    )
    if approval.proposal_sha256 != sha256_file(paths.proposal_path):
        raise T17LivePreflightError(T17LivePreflightErrorCode.PROPOSAL_HASH_MISMATCH)
    _require_budget_binding(matrix, proposal, approval)
    if build_approved_live_config(registration, matrix, proposal, approval) != config:
        raise T17LivePreflightError(T17LivePreflightErrorCode.CONFIG_DRIFT)
    rebuilt = build_live_matrix(root, registration, registry, matrix.stage)
    if rebuilt != matrix:
        raise T17LivePreflightError(T17LivePreflightErrorCode.MATRIX_DRIFT)
    _require_trial_bindings(matrix, base_matrix)
    expected = EXPECTED_COUNTS[matrix.stage]
    if (matrix.scheduled_core_trials, matrix.scheduled_replay_pairs) != expected:
        raise T17LivePreflightError(T17LivePreflightErrorCode.COUNT_INVALID)
    source_hashes = _source_hashes(root)
    matrix_sha = sha256_file(paths.matrix_path)
    preregistration_sha = sha256_file(paths.preregistration_path)
    registry_sha = sha256_file(paths.registry_path)
    base_matrix_sha = sha256_file(paths.base_matrix_path)
    proposal_sha = sha256_file(paths.proposal_path)
    approval_sha = sha256_file(paths.approval_path)
    config_sha = canonical_sha256(config.model_dump(mode="json"))
    payload = {
        "protocol_id": "t17-live-reference-v1",
        "stage": matrix.stage.value,
        "matrix_id": matrix.id,
        "provider": config.provider.model_dump(mode="json"),
        "budget": config.budget.model_dump(mode="json"),
        "scheduled_core_trials": matrix.scheduled_core_trials,
        "scheduled_replay_pairs": matrix.scheduled_replay_pairs,
        "matrix_sha256": matrix_sha,
        "preregistration_sha256": preregistration_sha,
        "scenario_registry_sha256": registry_sha,
        "base_matrix_sha256": base_matrix_sha,
        "budget_proposal_sha256": proposal_sha,
        "budget_approval_sha256": approval_sha,
        "approved_config_sha256": config_sha,
        "source_hashes": source_hashes,
    }
    return T17LivePreflightManifest(
        stage=matrix.stage,
        created_at=created_at,
        matrix_id=matrix.id,
        provider_model_id=config.provider.model_id,
        provider_model_revision=config.provider.model_revision,
        scheduled_core_trials=matrix.scheduled_core_trials,
        scheduled_replay_pairs=matrix.scheduled_replay_pairs,
        matrix_sha256=matrix_sha,
        preregistration_sha256=preregistration_sha,
        scenario_registry_sha256=registry_sha,
        base_matrix_sha256=base_matrix_sha,
        budget_proposal_sha256=proposal_sha,
        budget_approval_sha256=approval_sha,
        approved_config_sha256=config_sha,
        source_hashes=source_hashes,
        phase_contract_sha256=canonical_sha256(payload),
    )


def verify_live_preflight(
    paths: T17LivePreflightPaths,
    config: T17ApprovedLiveConfig,
    manifest: T17LivePreflightManifest,
) -> None:
    """在进入执行路径前重建完整合同，拒绝 approval 后任何漂移。"""
    rebuilt = build_live_preflight(paths, config, manifest.created_at)
    if rebuilt != manifest:
        raise T17LivePreflightError(T17LivePreflightErrorCode.EXECUTION_DRIFT)


def canonical_sha256(value: CanonicalValue) -> str:
    """对阶段合同使用固定 JSON 编码。"""
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require_budget_binding(
    matrix: T17LiveMatrix,
    proposal: T17BudgetProposal,
    approval: T17BudgetApproval,
) -> None:
    if matrix.budget.allow_live:
        raise T17LivePreflightError(T17LivePreflightErrorCode.STATIC_LIVE_ENABLED)
    values_match = (
        proposal.stage is matrix.stage
        and approval.stage is matrix.stage
        and proposal.model_id == matrix.provider.model_id
        and proposal.model_revision == matrix.provider.model_revision
        and proposal.requested_max_total_usd <= matrix.budget.max_total_usd
        and proposal.requested_max_cost_per_run_usd <= matrix.budget.max_cost_per_run_usd
        and approval.approved_max_total_usd == proposal.requested_max_total_usd
        and approval.approved_max_cost_per_run_usd == proposal.requested_max_cost_per_run_usd
    )
    if not values_match:
        raise T17LivePreflightError(T17LivePreflightErrorCode.BUDGET_BINDING_INVALID)


def _require_trial_bindings(
    matrix: T17LiveMatrix,
    base_matrix: ExperimentMatrix,
) -> None:
    variants = {item.variant: item for item in base_matrix.variants}
    for trial in matrix.trials:
        variant = variants.get(trial.source_variant)
        if variant is None or variant.scenario != trial.scenario:
            raise T17LivePreflightError(
                T17LivePreflightErrorCode.TRIAL_BINDING_INVALID,
                trial.trial_id,
            )


def _source_hashes(
    root: Path,
) -> dict[str, str]:
    files = [
        *sorted((root / "src" / "skillflow").rglob("*.py")),
        *sorted((root / "schemas").glob("t17-*.json")),
        *sorted(
            path
            for directory in ("experiments/t17", "scenarios", "configs", "integrations")
            for path in (root / directory).rglob("*")
            if path.is_file()
        ),
        root / "pyproject.toml",
    ]
    return {
        path.relative_to(root).as_posix(): sha256_file(path) for path in files if path.is_file()
    }
