"""第二版预注册与任务表，明确区分历史文件和新运行。"""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from skillflow.experiment.t16.provider import ProviderConfig
from skillflow.experiment.t17.live_matrix import T17LiveStage, T17SemanticTemplate
from skillflow.experiment.t17.minimal.contracts import NormalTaskContract, Sha256
from skillflow.experiment.t17.v2.catalog_models import SkillCatalog
from skillflow.experiment.t17.v2.claim_models import ClaimActionSpec
from skillflow.experiment.t17.v2.paired_models import SessionPairDesign
from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.enums import EnforcementMode
from skillflow.models.matrix import ExperimentVariant
from skillflow.models.matrix_design import HiaaDesign


class V2Configuration(StrictModel):
    """冻结普通任务、技能目录、统计、提示与失败规则；不含密钥。"""

    schema_version: Literal["2.0"] = "2.0"
    protocol_id: NonEmptyStr = "t17-live-reference-v2"
    prompt_contract_id: NonEmptyStr = "t17-reference-normal-task-v2"
    evaluator_version: Literal["2.0.0"] = "2.0.0"
    catalog: SkillCatalog
    tasks: Annotated[tuple[NormalTaskContract, ...], Field(min_length=1)]
    templates: Annotated[tuple[T17SemanticTemplate, ...], Field(min_length=1)]
    repeats: Annotated[int, Field(ge=1)] = 3
    model1: ProviderConfig
    model2: ProviderConfig
    hiaa_designs: tuple[HiaaDesign, ...] = ()
    session_pairs: tuple[SessionPairDesign, ...] = ()
    claim_bindings: dict[NonEmptyStr, tuple[ClaimActionSpec, ...]] = Field(default_factory=dict)
    replay_source: Literal["same_actual_core_checkpoint"] = "same_actual_core_checkpoint"
    valid_only_hiaa: Literal["complete_behavior_valid_four_cells"] = (
        "complete_behavior_valid_four_cells"
    )
    alr_no_neutral_request: Literal["no_receipt_with_closed_replay_not_fake_baseline"] = (
        "no_receipt_with_closed_replay_not_fake_baseline"
    )
    bootstrap_seed: Literal[17017] = 17017
    bootstrap_resamples: Literal[10000] = 10000
    price_basis_date: Literal["2026-09-03"] = "2026-09-03"
    recheck_prices: Literal[False] = False
    paid_calls_authorized: Literal[False] = False
    missing_dependency: Literal["record_and_skip_step"] = "record_and_skip_step"
    absent_replay_target: Literal["not_applicable_with_evidence"] = "not_applicable_with_evidence"
    model_failure: Literal["record_without_resampling"] = "record_without_resampling"
    infrastructure_failure: Literal["stop_attempt_keep_partial"] = "stop_attempt_keep_partial"

    @model_validator(mode="after")
    def validate_task_bindings(self) -> Self:
        """任务、目录和模板身份完整且唯一。"""
        tasks = {item.scenario_path: item for item in self.tasks}
        if len(tasks) != len(self.tasks):
            raise ValueError("v2_duplicate_task_contract")
        if any(item.scenario_path not in tasks for item in self.catalog.variants):
            raise ValueError("v2_catalog_task_missing")
        if len({item.template_id for item in self.templates}) != len(self.templates):
            raise ValueError("v2_duplicate_semantic_template")
        if set(self.claim_bindings) != {item.skill_variant_id for item in self.catalog.variants}:
            raise ValueError("v2_claim_binding_catalog_coverage")
        return self


class V2Trial(StrictModel):
    """每条任务完整保存可比较的技能和运行条件身份。"""

    trial_id: NonEmptyStr
    condition_id: NonEmptyStr
    source_variant: NonEmptyStr
    configuration: ExperimentVariant
    skill_variant_id: NonEmptyStr
    skill_content_sha256: Sha256
    manifest_sha256: Sha256
    task_contract_id: NonEmptyStr
    task_contract_sha256: Sha256
    semantic_instance_id: NonEmptyStr
    semantic_template_id: NonEmptyStr
    repeat_index: Annotated[int, Field(ge=1)]
    task_prompt: NonEmptyStr
    defense_base_id: Sha256
    enforcement_mode: EnforcementMode
    replay_pair_ids: dict[NonEmptyStr, NonEmptyStr]


class V2Matrix(StrictModel):
    """一个模型阶段的完整调度，与旧 T17 格式不能混用。"""

    schema_version: Literal["2.0"] = "2.0"
    protocol_id: NonEmptyStr
    matrix_id: NonEmptyStr
    stage: T17LiveStage
    configuration_sha256: Sha256
    catalog_sha256: Sha256
    provider: ProviderConfig
    scheduled_core_trials: Annotated[int, Field(ge=1)]
    scheduled_replay_pairs: Annotated[int, Field(ge=0)]
    trials: Annotated[tuple[V2Trial, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def validate_schedule(self) -> Self:
        """不能通过改计数字段缩小分母或重用任务与重放身份。"""
        identifiers = tuple(item.trial_id for item in self.trials)
        pairs = tuple(value for item in self.trials for value in item.replay_pair_ids.values())
        if len(set(identifiers)) != len(identifiers) or len(set(pairs)) != len(pairs):
            raise ValueError("v2_duplicate_scheduled_unit")
        if (
            len(self.trials) != self.scheduled_core_trials
            or len(pairs) != self.scheduled_replay_pairs
        ):
            raise ValueError("v2_scheduled_count_mismatch")
        return self
