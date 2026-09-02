"""T17 Live 阶段的批准、预检、Trial 与阶段摘要合同。"""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum, unique
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from skillflow.experiment.t17.contracts import HookCapability, RatioMeasurement
from skillflow.experiment.t17.live_matrix import T17LiveStage
from skillflow.experiment.t17.live_reference_client import ReferenceLiveTelemetry
from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.enums import EnforcementMode

NonNegativeInt = Annotated[int, Field(ge=0)]
PositiveInt = Annotated[int, Field(ge=1)]
NonNegativeMoney = Annotated[Decimal, Field(ge=0)]
PositiveMoney = Annotated[Decimal, Field(gt=0)]
Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


@unique
class T17LiveUnitKind(StrEnum):
    """Live 调度中的核心 Run 或成对 Replay。"""

    CORE = "core"
    REPLAY = "replay"


@unique
class T17LiveTerminalStatus(StrEnum):
    """一条调度单元的持久化终态。"""

    COMPLETED = "completed"
    INCOMPLETE = "incomplete"
    FAILED = "failed"


@unique
class T17LiveFailureKind(StrEnum):
    """不得混为一个 invalid 桶的封闭失败类型。"""

    SCHEMA = "schema"
    PROVIDER_4XX = "provider_4xx"
    INFRASTRUCTURE = "infrastructure"
    BUDGET = "budget"
    MODEL_REVISION = "model_revision"
    EVIDENCE_BINDING = "evidence_binding"


class T17BudgetApproval(StrictModel):
    """预算提案经用户非秘密确认后的单阶段授权。"""

    schema_version: Literal["0.1"] = "0.1"
    stage: T17LiveStage
    approved_at: datetime
    authorization_status: Literal["approved_by_user"] = "approved_by_user"
    proposal_sha256: Sha256Hex
    approved_max_total_usd: PositiveMoney
    approved_max_cost_per_run_usd: PositiveMoney

    @model_validator(mode="after")
    def require_nested_limit(self) -> Self:
        """单 Run 批准不得超过阶段总批准。"""
        if self.approved_max_cost_per_run_usd > self.approved_max_total_usd:
            raise PydanticCustomError(
                "t17_approval_run_exceeds_total",
                "单 Run 批准不得超过阶段总批准",
            )
        return self


class T17LivePreflightManifest(StrictModel):
    """在首次 API 调用前冻结的阶段合同。"""

    schema_version: Literal["0.1"] = "0.1"
    protocol_id: Literal["t17-live-reference-v1"] = "t17-live-reference-v1"
    stage: T17LiveStage
    created_at: datetime
    matrix_id: NonEmptyStr
    provider_model_id: NonEmptyStr
    provider_model_revision: NonEmptyStr
    scheduled_core_trials: PositiveInt
    scheduled_replay_pairs: NonNegativeInt
    matrix_sha256: Sha256Hex
    preregistration_sha256: Sha256Hex
    scenario_registry_sha256: Sha256Hex
    base_matrix_sha256: Sha256Hex
    budget_proposal_sha256: Sha256Hex
    budget_approval_sha256: Sha256Hex
    approved_config_sha256: Sha256Hex
    source_hashes: dict[NonEmptyStr, Sha256Hex]
    phase_contract_sha256: Sha256Hex


class T17ArtifactDigest(StrictModel):
    """Trial 结果绑定的项目内相对路径与字节哈希。"""

    relative_path: NonEmptyStr
    sha256: Sha256Hex


class T17ProviderFailureDiagnostic(StrictModel):
    """Provider 错误的安全 status/type/code/param 白名单字段。"""

    status_code: int | None = None
    provider_type: NonEmptyStr | None = None
    provider_code: NonEmptyStr | None = None
    provider_param: NonEmptyStr | None = None


class T17LiveUnitRecord(StrictModel):
    """一条核心 Run 或 Replay pair 的不可变 Raw 索引。"""

    schema_version: Literal["0.1"] = "0.1"
    sequence: PositiveInt
    stage: T17LiveStage
    unit_id: NonEmptyStr
    trial_id: NonEmptyStr
    unit_kind: T17LiveUnitKind
    variant: NonEmptyStr
    source_variant: NonEmptyStr
    enforcement_mode: EnforcementMode
    scenario_id: NonEmptyStr
    semantic_instance_id: NonEmptyStr
    semantic_template_id: NonEmptyStr
    repeat_index: PositiveInt
    terminal_status: T17LiveTerminalStatus
    failure_kind: T17LiveFailureKind | None = None
    failure_detail: NonEmptyStr | None = None
    failure_diagnostic: T17ProviderFailureDiagnostic | None = None
    telemetry: ReferenceLiveTelemetry
    run_ids: tuple[NonEmptyStr, ...]
    replay_ids: tuple[NonEmptyStr, ...]
    task_success: bool | None
    safe_task_success: bool | None
    evidence_ids: tuple[NonEmptyStr, ...]
    artifacts: tuple[T17ArtifactDigest, ...]

    @model_validator(mode="after")
    def require_terminal_contract(self) -> Self:
        """完成与失败必须有互斥且足够的结构化证据。"""
        completed = self.terminal_status is T17LiveTerminalStatus.COMPLETED
        if completed and (self.failure_kind is not None or self.failure_detail is not None):
            self._invalid("完成单元不得包含 failure")
        if completed and self.failure_diagnostic is not None:
            self._invalid("完成单元不得包含 Provider failure diagnostic")
        if not completed and self.failure_kind is None:
            self._invalid("非完成单元必须声明 failure_kind")
        if completed and not self.artifacts:
            self._invalid("完成单元必须绑定产物哈希")
        if self.unit_kind is T17LiveUnitKind.CORE:
            if completed and (len(self.run_ids) != 1 or self.task_success is None):
                self._invalid("完成核心单元必须绑定一个 Run 与 Task Success")
            if self.replay_ids or (self.task_success is None) is not (
                self.safe_task_success is None
            ):
                self._invalid("核心单元的 Replay/Task 字段不一致")
        elif self.run_ids or self.task_success is not None or self.safe_task_success is not None:
            self._invalid("Replay 单元不得伪装核心 Task 结果")
        return self

    @staticmethod
    def _invalid(detail: str) -> None:
        raise PydanticCustomError("t17_live_unit_record_invalid", detail)


class T17LiveStageSummary(StrictModel):
    """单模型单阶段的完整性、用量与阶段门摘要。"""

    schema_version: Literal["0.1"] = "0.1"
    stage: T17LiveStage
    model_id: NonEmptyStr
    model_revision: NonEmptyStr
    scheduled_core_trials: PositiveInt
    scheduled_replay_pairs: NonNegativeInt
    completed_core_trials: NonNegativeInt
    completed_replay_pairs: NonNegativeInt
    completion: RatioMeasurement
    task_success_evidence_coverage: RatioMeasurement
    receipt_coverage: RatioMeasurement
    actual_usage_coverage: RatioMeasurement
    replay_influence_coverage: RatioMeasurement
    required_hook_coverage: RatioMeasurement
    hooks: tuple[HookCapability, ...]
    telemetry: ReferenceLiveTelemetry
    schema_failure_count: NonNegativeInt
    provider_4xx_count: NonNegativeInt
    infrastructure_failure_count: NonNegativeInt
    evidence_binding_failure_count: NonNegativeInt
    budget_stop_count: NonNegativeInt
    revision_drift_count: NonNegativeInt
    refusal_count: NonNegativeInt
    no_call_count: NonNegativeInt
    live_gate_passed: bool
    stop_detail: NonEmptyStr | None = None
    preflight_sha256: Sha256Hex
    usage_journal_sha256: Sha256Hex
    trial_results_sha256: Sha256Hex
