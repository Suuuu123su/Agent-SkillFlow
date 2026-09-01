"""T16-D.2 之前不可执行的 v3 bridge/calibration 预注册模型。"""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from skillflow.experiment.t16.budget import BudgetConfig
from skillflow.experiment.t16.preregistration_models import IndependentFactor, PairRole
from skillflow.experiment.t16.provider import ProviderConfig
from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.matrix_design import HiaaCell
from skillflow.models.references import EffectSelectorRef, ScenarioPath

PositiveInt = Annotated[int, Field(ge=1)]


class PromptContractV3(StrictModel):
    """只扩展结构化任务结果，不改变安全实验变量。"""

    id: NonEmptyStr
    version: Literal["3.0"] = "3.0"
    instruction: NonEmptyStr
    structured_result_schema_id: NonEmptyStr
    paired_conditions_share_schema: Literal[True] = True
    old_v2_mergeable: Literal[False] = False


class BridgeSemanticTemplate(StrictModel):
    """一个保持原任务含义的 v3 语义实例。"""

    template_id: NonEmptyStr
    task_prompt: NonEmptyStr


class BridgeSemanticInstanceSet(StrictModel):
    """Smoke 固定使用的两条语义等价实例。"""

    instance_set_id: NonEmptyStr
    templates: Annotated[tuple[BridgeSemanticTemplate, ...], Field(min_length=2, max_length=2)]


class TaskSuccessConditionRegistration(StrictModel):
    """v3 Matrix 需要的条件级冻结引用。"""

    condition_id: NonEmptyStr
    scenario: ScenarioPath
    pair_group_id: NonEmptyStr
    pair_role: PairRole
    independent_factor: IndependentFactor
    instance_set_id: NonEmptyStr
    task_success_spec_id: NonEmptyStr
    task_output_contract_id: NonEmptyStr
    target_effect_selectors: Annotated[tuple[EffectSelectorRef, ...], Field(min_length=1)]
    observation_sessions: tuple[int, ...] = ()
    hiaa_cell: HiaaCell | None = None
    hiaa_design_id: NonEmptyStr | None = None
    harm_selector: EffectSelectorRef | None = None


class TaskSuccessPreregistrationV3(StrictModel):
    """48 链 bridge/calibration Smoke 的完整离线锁。"""

    schema_version: Literal["0.3", "0.3.1"] = "0.3"
    protocol_version: Literal["3.0", "3.1"] = "3.0"
    id: NonEmptyStr
    study_role: Literal["bridge_calibration"] = "bridge_calibration"
    parent_preregistration_id: NonEmptyStr
    task_success_specification_id: NonEmptyStr
    evaluator_id: NonEmptyStr
    evaluator_version: NonEmptyStr
    prompt_contract: PromptContractV3
    semantic_instances_per_condition: Literal[2] = 2
    repeats_per_instance: Literal[2] = 2
    instance_sets: Annotated[tuple[BridgeSemanticInstanceSet, ...], Field(min_length=1)]
    conditions: Annotated[
        tuple[TaskSuccessConditionRegistration, ...],
        Field(min_length=12, max_length=12),
    ]
    provider: ProviderConfig
    budget: BudgetConfig
    stop_conditions: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def require_closed_offline_design(self) -> Self:
        """验证引用、配对、HIAA 和 live 默认关闭。"""
        expected_protocol = "3.1" if self.schema_version == "0.3.1" else "3.0"
        if self.protocol_version != expected_protocol:
            self._invalid("schema_version 与 protocol_version 不一致")
        if self.budget.allow_live:
            self._invalid("v3 预注册默认必须关闭 live")
        set_ids = tuple(item.instance_set_id for item in self.instance_sets)
        condition_ids = tuple(item.condition_id for item in self.conditions)
        if len(set(set_ids)) != len(set_ids) or len(set(condition_ids)) != len(condition_ids):
            self._invalid("实例集合或 condition_id 不得重复")
        if any(item.instance_set_id not in set(set_ids) for item in self.conditions):
            self._invalid("条件引用了不存在的实例集合")
        self._require_pair_contracts()
        self._require_hiaa_contract()
        return self

    def _require_pair_contracts(self) -> None:
        groups: dict[str, list[TaskSuccessConditionRegistration]] = {}
        for condition in self.conditions:
            groups.setdefault(condition.pair_group_id, []).append(condition)
        for group in groups.values():
            if len(group) == 1:
                if group[0].pair_role is not PairRole.STANDALONE:
                    self._invalid("单条件组必须是 standalone")
                continue
            if len({item.task_output_contract_id for item in group}) != 1:
                self._invalid("paired conditions 必须共享 task output contract")
            if len({item.instance_set_id for item in group}) != 1:
                self._invalid("paired conditions 必须共享语义实例")
            if len({item.observation_sessions for item in group}) != 1:
                self._invalid("paired conditions 必须共享 Session 结构")
            if len({item.target_effect_selectors for item in group}) != 1:
                self._invalid("paired conditions 必须共享 Effect selector")

    def _require_hiaa_contract(self) -> None:
        hiaa = tuple(item for item in self.conditions if item.hiaa_cell is not None)
        if {item.hiaa_cell for item in hiaa} != set(HiaaCell):
            self._invalid("C1 HIAA 必须完整包含四格")
        if len({item.hiaa_design_id for item in hiaa}) != 1:
            self._invalid("C1 HIAA 必须共享设计 ID")
        if len({item.harm_selector for item in hiaa}) != 1:
            self._invalid("C1 HIAA 必须共享 harm_selector")

    @staticmethod
    def _invalid(detail: str) -> None:
        raise PydanticCustomError("t16_task_success_prereg_invalid", detail)
