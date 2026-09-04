"""第二版阶段身份、逐调度终态与完整性门，不与历史协议混用。"""

from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from skillflow.benchmark.replay_models import ReplayPairManifest
from skillflow.experiment.t17.contracts import MeasurementStatus
from skillflow.experiment.t17.live_matrix import T17LiveStage
from skillflow.experiment.t17.minimal.contracts import Sha256
from skillflow.experiment.t17.v2.frozen import FrozenFile
from skillflow.experiment.t17.v2.portable_models import PortableCore, PortableRun
from skillflow.experiment.t17.v2.runtime_models import DecisionFact, ExecutionIssue
from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.enums import Decision, EnforcementMode
from skillflow.models.scenario_parts import EffectSelector

V2Domain = Literal["scripted", "fake_reference", "live_reference"]
TerminalStatus = Literal[
    "completed",
    "not_applicable",
    "evidence_binding_failure",
    "infrastructure_invalid",
    "protocol_error",
    "budget_exhausted",
    "not_run",
]
Nonnegative = Annotated[int, Field(ge=0)]
Money = Annotated[Decimal, Field(ge=0)]


class UnitUsage(StrictModel):
    """实际返回用量与保守占用分开；费用始终是估算，不冒充账单。"""

    complete: bool = True
    missing_reason: NonEmptyStr | None = None
    api_calls: Nonnegative = 0
    responses: Nonnegative = 0
    input_tokens: Nonnegative = 0
    cached_input_tokens: Nonnegative = 0
    cache_write_tokens: Nonnegative = 0
    output_tokens: Nonnegative = 0
    reasoning_tokens: Nonnegative = 0
    latency_ms: Annotated[float, Field(ge=0, allow_inf_nan=False)] = 0
    estimated_cost_usd: Money = Decimal(0)
    reserved_cost_usd: Money = Decimal(0)
    response_ids: tuple[NonEmptyStr, ...] = ()


class PhaseContract(StrictModel):
    """请求前冻结的阶段合同；运行中不准调整配置、脚本或统计。"""

    schema_version: Literal["2.0"] = "2.0"
    protocol_id: NonEmptyStr
    stage: T17LiveStage
    domain: V2Domain
    configuration_sha256: Sha256
    matrix_sha256: Sha256
    catalog_sha256: Sha256
    runtime_files: dict[NonEmptyStr, FrozenFile]
    scheduled_core: Nonnegative
    scheduled_replay: Nonnegative
    evaluator_version: Literal["2.0.0"] = "2.0.0"
    external_effects_simulated: Literal[True] = True
    independent_review: Literal["REVIEW_UNAVAILABLE"] = "REVIEW_UNAVAILABLE"


class UnitIdentity(StrictModel):
    """每条公开记录的任务、技能、模型、防御与统计簇身份。"""

    protocol_id: NonEmptyStr
    stage: T17LiveStage
    domain: V2Domain
    phase_contract_sha256: Sha256
    matrix_sha256: Sha256
    unit_id: NonEmptyStr
    trial_id: NonEmptyStr
    condition_id: NonEmptyStr
    source_variant: NonEmptyStr
    skill_variant_id: NonEmptyStr
    skill_content_sha256: Sha256
    manifest_sha256: Sha256
    task_contract_id: NonEmptyStr
    task_contract_sha256: Sha256
    semantic_template_id: NonEmptyStr
    semantic_instance_id: NonEmptyStr
    repeat_index: Annotated[int, Field(ge=1)]
    defense_base_id: Sha256
    enforcement_mode: EnforcementMode
    requested_model: NonEmptyStr
    model_revision: NonEmptyStr


class CoreTerminal(StrictModel):
    """任务失败也是 completed；只有证据缺失或中断才不可评估。"""

    schema_version: Literal["2.0"] = "2.0"
    identity: UnitIdentity
    status: TerminalStatus
    reason: NonEmptyStr | None = None
    run_id: NonEmptyStr | None = None
    data: PortableCore | None = None
    decisions: tuple[DecisionFact, ...] = ()
    issues: tuple[ExecutionIssue, ...] = ()
    usage: UnitUsage = UnitUsage()
    wall_latency_ms: Annotated[float, Field(ge=0)] = 0
    raw_files: dict[NonEmptyStr, FrozenFile] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_terminal(self) -> Self:
        """没有事实不能声称完成；失败必须有原因。"""
        if self.status == "completed":
            if (
                self.data is None
                or self.reason is not None
                or self.run_id != self.data.facts.run_id
            ):
                raise ValueError("v2_core_completion_without_evidence")
        elif self.reason is None or self.status == "not_applicable":
            raise ValueError("v2_core_terminal_reason")
        return self


class ReplayProof(StrictModel):
    """只比较选择器命中且有回执的分支后缀操作。"""

    selector: EffectSelector
    source: PortableRun
    original: PortableRun
    neutral: PortableRun
    manifest: ReplayPairManifest
    y_original: bool
    y_neutral: bool
    ci: Literal[-1, 0, 1]
    original_effect_ids: tuple[NonEmptyStr, ...]
    neutral_effect_ids: tuple[NonEmptyStr, ...]
    original_baseline: Decision | None
    neutral_baseline: Decision | None
    evidence_ids: tuple[NonEmptyStr, ...]


class ReplayTerminal(StrictModel):
    """未产生干预目标以有来源证据的不适用终态保留，不能填 CI=0。"""

    schema_version: Literal["2.0"] = "2.0"
    identity: UnitIdentity
    source_core_run_id: NonEmptyStr | None
    target_alias: NonEmptyStr
    status: TerminalStatus
    reason: NonEmptyStr | None = None
    proof: ReplayProof | None = None
    absent_source: PortableRun | None = None
    decisions: tuple[DecisionFact, ...] = ()
    issues: tuple[ExecutionIssue, ...] = ()
    usage: UnitUsage = UnitUsage()
    raw_files: dict[NonEmptyStr, FrozenFile] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_terminal(self) -> Self:
        """检查点证明或真实缺失路径必须与终态一致。"""
        if self.status == "completed" and (self.proof is None or self.reason is not None):
            raise ValueError("v2_replay_completion_without_evidence")
        if self.status == "not_applicable" and (
            self.absent_source is None or self.proof is not None
        ):
            raise ValueError("v2_replay_absence_without_evidence")
        if self.status != "completed" and self.reason is None:
            raise ValueError("v2_replay_terminal_reason")
        return self


class PhaseGate(StrictModel):
    """只以预先冻结的调度和可信证据覆盖判断阶段是否完整。"""

    passed: bool
    scheduled_core: Nonnegative
    scheduled_replay: Nonnegative
    terminal_core: Nonnegative
    terminal_replay: Nonnegative
    completed_core: Nonnegative
    evaluated_replay: Nonnegative
    not_applicable_replay: Nonnegative
    infrastructure_invalid: Nonnegative
    protocol_errors: Nonnegative
    binding_failures: Nonnegative
    task_evidence_coverage: Annotated[float, Field(ge=0, le=1)]
    receipt_coverage: Annotated[float, Field(ge=0, le=1)]
    required_hook_coverage: Annotated[float, Field(ge=0, le=1)]
    binding_coverage: Annotated[float, Field(ge=0, le=1)] = 0
    usage_complete: bool = False
    metric_statuses: dict[NonEmptyStr, MeasurementStatus] = Field(default_factory=dict)
    failures: tuple[NonEmptyStr, ...]


class StageResult(StrictModel):
    """一个独立尝试的结果，不能拼接不同尝试。"""

    phase: PhaseContract
    source_phases: tuple[PhaseContract, ...] = ()
    cores: tuple[CoreTerminal, ...]
    replays: tuple[ReplayTerminal, ...]
    gate: PhaseGate
