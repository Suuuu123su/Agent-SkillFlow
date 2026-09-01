"""T16-D.2 原始记录、门禁、检查点与阶段摘要模型。"""

from decimal import Decimal
from enum import StrEnum, unique
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, Field, model_validator
from pydantic_core import PydanticCustomError

from skillflow.experiment.t16.live_records import LiveTrialRecord
from skillflow.experiment.t16.provider import TokenUsage
from skillflow.experiment.t16.task_success_facts import PlatformEvidenceSnapshot
from skillflow.models.base import NonEmptyStr, StrictModel

Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
NonNegativeInt = Annotated[int, Field(ge=0)]
NonNegativeMoney = Annotated[Decimal, Field(ge=0)]


@unique
class T16D2StopReason(StrEnum):
    """付费桥接阶段可能触发的封闭停止原因。"""

    CANARY_GATE_BLOCKED = "canary_gate_blocked"
    BUDGET_LIMIT = "budget_limit"
    P95_BUDGET_PREDICTION = "p95_budget_prediction"
    MODEL_REVISION_CHANGED = "model_revision_changed"
    INFRASTRUCTURE_RATE = "infrastructure_rate"
    TECHNICAL_NOT_EVALUABLE = "technical_not_evaluable"
    EVIDENCE_BINDING = "evidence_binding"
    SECRET_SCAN = "secret_scan"  # noqa: S105 - 这是停止原因标签，不是凭据。
    GATEWAY_CRASH = "gateway_crash"


class T16D2RawTrialRecord(StrictModel):
    """一行原子保存 LiveTrialRecord 与其可复算平台快照。"""

    schema_version: Literal["0.1"] = "0.1"
    study_role: Literal["bridge_calibration"] = "bridge_calibration"
    task_success_spec_id: NonEmptyStr
    provider_model_revisions: tuple[NonEmptyStr, ...]
    platform_evidence_snapshot: PlatformEvidenceSnapshot
    live_trial: LiveTrialRecord

    @model_validator(mode="after")
    def require_platform_binding(self) -> Self:
        """拒绝 Artifact、Receipt 或 Session 与 Live Trial 错配。"""
        record = self.live_trial
        if record.schema_version != "0.3" or record.run_id is None:
            self._invalid("D.2 必须保存 v0.3 LiveTrialRecord 与 Run ID")
        snapshot = self.platform_evidence_snapshot
        if any(item.run_id != record.run_id for item in snapshot.artifacts):
            self._invalid("Artifact 与 Live Run 不一致")
        if any(item.trial_id != record.result.trial_id for item in snapshot.artifacts):
            self._invalid("Artifact 与 Live Trial 不一致")
        if any(item.run_id != record.run_id for item in snapshot.receipts):
            self._invalid("Receipt 与 Live Run 不一致")
        session_ids = {f"session-{item.session_index}" for item in record.sessions}
        if {item.session_id for item in snapshot.sessions} != session_ids:
            self._invalid("Session Trace 与 Live Session 不一致")
        audit_receipts = {
            call.receipt_id
            for session in record.sessions
            for call in session.tool_calls
            if call.receipt_id is not None
        }
        snapshot_receipts = {item.receipt_id for item in snapshot.receipts}
        if audit_receipts != snapshot_receipts:
            self._invalid("Tool audit 与平台 Receipt 集合不一致")
        return self

    @staticmethod
    def _invalid(detail: str) -> None:
        raise PydanticCustomError("t16d2_raw_record_inconsistent", detail)


class T16D2PreflightManifest(StrictModel):
    """首次 API 请求前冻结的文件、代码与合同指纹。"""

    schema_version: Literal["0.1"] = "0.1"
    created_at: AwareDatetime
    matrix_sha256: Sha256Hex
    preregistration_sha256: Sha256Hex
    task_success_specification_sha256: Sha256Hex
    prompt_contract_sha256: Sha256Hex
    phase_contract_sha256: Sha256Hex
    v2_frozen_hashes: dict[NonEmptyStr, Sha256Hex]
    source_hashes: dict[NonEmptyStr, Sha256Hex]
    matrix_trial_count: Literal[48] = 48
    trial_ids_unique: Literal[True] = True
    pairs_complete: Literal[True] = True
    evaluator_version: Literal["1.0.0"] = "1.0.0"


class T16D2StageGate(StrictModel):
    """Canary 或完整阶段的技术证据门禁。"""

    schema_version: Literal["0.1"] = "0.1"
    stage: Literal["canary", "final"]
    created_at: AwareDatetime
    expected: NonNegativeInt
    observed: NonNegativeInt
    passed: bool
    reasons: tuple[NonEmptyStr, ...]
    evidence_count: NonNegativeInt
    not_evaluable_assertion_count: NonNegativeInt
    infrastructure_invalid_count: NonNegativeInt
    provider_model_revisions: tuple[NonEmptyStr, ...]
    artifact_binding_valid: bool
    receipt_binding_valid: bool
    session_binding_valid: bool
    secret_scan_passed: bool


class T16D2Checkpoint(StrictModel):
    """阶段内不可变累计检查点。"""

    schema_version: Literal["0.1"] = "0.1"
    created_at: AwareDatetime
    observed: NonNegativeInt
    scheduled: Literal[48] = 48
    conservative_reserved_usd: NonNegativeMoney
    actual_estimated_cost_usd: NonNegativeMoney
    token_usage: TokenUsage
    raw_records_sha256: Sha256Hex


class T16D2RunSummary(StrictModel):
    """D.2 执行状态；不包含 Prompt、响应或凭据。"""

    schema_version: Literal["0.1"] = "0.1"
    created_at: AwareDatetime
    scheduled: Literal[48] = 48
    observed: NonNegativeInt
    unrun: NonNegativeInt
    canary_observed: NonNegativeInt
    canary_gate_passed: bool
    final_gate_passed: bool
    stop_reason: T16D2StopReason | None = None
    stop_detail: NonEmptyStr | None = None
    infrastructure_invalid: NonNegativeInt
    conservative_reserved_usd: NonNegativeMoney
    actual_estimated_cost_usd: NonNegativeMoney
    token_usage: TokenUsage
    api_call_count: NonNegativeInt
    raw_records_sha256: Sha256Hex
