"""最小技术验收的运行域、事实记录与哈希清单。"""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from skillflow.experiment.t17.contracts import HookCapability, MeasurementStatus
from skillflow.experiment.t17.minimal.contracts import Sha256
from skillflow.experiment.t17.minimal.task_models import NormalTaskEvidence
from skillflow.experiment.t17.observation_models import ReferenceObservationSnapshot
from skillflow.models.base import NonEmptyStr, StrictModel

MinimalDomain = Literal["scripted", "fake_reference"]
Behavior = Literal["normal", "refusal", "no_call", "schema_rejection", "infrastructure_invalid"]


class FakeDecisionRecord(StrictModel):
    """无正文的 Fake 决策日志；不冒充真实 API 响应或 Token。"""

    sequence: Annotated[int, Field(ge=1)]
    allowed_action_ids: tuple[NonEmptyStr, ...]
    selected_action_ids: tuple[NonEmptyStr, ...]
    behavior: Behavior
    schema_valid: bool


class MinimalRunRecord(StrictModel):
    """一条完整 core 的受信事实；普通任务与旧结构投影明确分开。"""

    schema_version: Literal["1.0"] = "1.0"
    domain: MinimalDomain
    simulation_only: Literal[True] = True
    external_effects_simulated: Literal[True] = True
    run_id: NonEmptyStr
    variant: NonEmptyStr
    phase_contract_sha256: Sha256
    artifact_ids_by_alias: dict[NonEmptyStr, NonEmptyStr]
    receipt_artifact_ids: tuple[NonEmptyStr, ...]
    runtime: ReferenceObservationSnapshot
    task: NormalTaskEvidence
    hooks: tuple[HookCapability, ...]
    step_event_ids: tuple[NonEmptyStr, ...]
    decision_journal: tuple[FakeDecisionRecord, ...]
    actual_api_calls: Literal[0] = 0
    harness_wall_latency_ms: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    terminal_status: Literal["completed"] = "completed"

    @model_validator(mode="after")
    def validate_version_and_domain(self) -> Self:
        """拒绝不同 Run、旧任务版本和跨执行域伪装。"""
        if self.runtime.run_id != self.run_id or self.task.run_id != self.run_id:
            raise ValueError("minimal_record_run_binding")
        if self.runtime.task_success is not None:
            raise ValueError("minimal_record_legacy_task_must_be_separate")
        if self.domain == "scripted" and self.decision_journal:
            raise ValueError("minimal_scripted_has_no_model_decisions")
        if self.domain == "fake_reference" and len(self.decision_journal) != len(
            self.step_event_ids
        ):
            raise ValueError("minimal_fake_decision_step_binding")
        if len({item.hook for item in self.hooks}) != len(self.hooks):
            raise ValueError("minimal_duplicate_hook")
        return self


class MinimalPhaseContract(StrictModel):
    """在第一次运行前冻结的零费用 Phase Contract。"""

    schema_version: Literal["1.0"] = "1.0"
    protocol_id: Literal["t17-minimal-technical-v1"] = "t17-minimal-technical-v1"
    domain: MinimalDomain
    configuration_sha256: Sha256
    matrix_sha256: Sha256
    runtime_source_sha256: dict[NonEmptyStr, Sha256]
    expected_core_runs: Literal[23] = 23
    expected_replay_pairs: Literal[12] = 12
    semantic_instances: Literal[1] = 1
    primary_repeats: Literal[1] = 1
    actual_api_call_limit: Literal[0] = 0
    external_effects_simulated: Literal[True] = True
    evaluator_version: Literal["2.0.0"] = "2.0.0"


class MinimalExecutionStatus(StrictModel):
    """零费用进程异常也留下显式 Partial，绝不恢复填充原目录。"""

    schema_version: Literal["1.0"] = "1.0"
    domain: MinimalDomain
    phase_contract_sha256: Sha256
    status: Literal[MeasurementStatus.MEASURED, MeasurementStatus.INCOMPLETE]
    expected_core_runs: Literal[23] = 23
    observed_core_runs: Annotated[int, Field(ge=0, le=23)]
    expected_replay_pairs: Literal[12] = 12
    observed_replay_pairs: Annotated[int, Field(ge=0, le=12)]
    actual_api_calls: Literal[0] = 0
    reason: NonEmptyStr | None = None

    @model_validator(mode="after")
    def validate_completion(self) -> Self:
        """完整调度与完成原因必须吻合，失败不能隐去。"""
        if self.status is MeasurementStatus.MEASURED:
            if (
                self.observed_core_runs != self.expected_core_runs
                or self.observed_replay_pairs != self.expected_replay_pairs
                or self.reason is not None
            ):
                raise ValueError("minimal_execution_status_false_completion")
        elif self.reason is None:
            raise ValueError("minimal_execution_status_incomplete_reason")
        return self


class FileDigest(StrictModel):
    """相对路径与字节哈希，不记录宿主路径或正文。"""

    path: NonEmptyStr
    sha256: Sha256
    size_bytes: Annotated[int, Field(ge=0)]
    jsonl_records: Annotated[int, Field(ge=0)] | None = None


class RawManifest(StrictModel):
    """一个域的不可变 Raw 文件集合；报告不进入 Raw 分母。"""

    schema_version: Literal["1.0"] = "1.0"
    domain: MinimalDomain
    phase_contract_sha256: Sha256
    files: Annotated[tuple[FileDigest, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def reject_duplicate_paths(self) -> Self:
        """重复路径不能掩盖缺失记录。"""
        paths = tuple(item.path for item in self.files)
        if len(set(paths)) != len(paths):
            raise ValueError("minimal_manifest_duplicate")
        return self
