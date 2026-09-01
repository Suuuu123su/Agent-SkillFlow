"""12 条件的 v3 Task Success specification 模型。"""

import hashlib
import json
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from skillflow.experiment.t16.task_success_assertions import TaskSuccessAssertion
from skillflow.models.base import NonEmptyStr, StrictModel


class TaskSuccessConditionSpecification(StrictModel):
    """一个条件的正常任务契约；危险 Effect 明确排除在外。"""

    spec_id: NonEmptyStr
    condition_id: NonEmptyStr
    normal_task_id: NonEmptyStr
    normal_task_description: NonEmptyStr
    task_output_contract_id: NonEmptyStr
    final_artifact_alias: NonEmptyStr
    output_schema_id: NonEmptyStr
    dangerous_effect_aliases_excluded: tuple[NonEmptyStr, ...]
    not_evaluable_rule: NonEmptyStr
    assertions: Annotated[tuple[TaskSuccessAssertion, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def require_unique_assertions_and_excluded_effects(self) -> Self:
        """拒绝重复断言或把危险 Effect 当成任务成功条件。"""
        assertion_ids = tuple(item.assertion_id for item in self.assertions)
        if len(assertion_ids) != len(set(assertion_ids)):
            self._invalid("同一 specification 的 assertion_id 不得重复")
        excluded = set(self.dangerous_effect_aliases_excluded)
        asserted_effects = {
            item.effect_alias for item in self.assertions if hasattr(item, "effect_alias")
        }
        if excluded & asserted_effects:
            self._invalid("危险 Effect 不得作为正常任务成功条件")
        if not any(item.required for item in self.assertions):
            self._invalid("每个 specification 至少包含一个 required assertion")
        return self

    @property
    def contract_fingerprint(self) -> str:
        """忽略 assertion ID，对实际判定能力生成稳定指纹。"""
        assertions = tuple(
            item.model_dump(mode="json", exclude={"assertion_id"}) for item in self.assertions
        )
        contract = {
            "normal_task_id": self.normal_task_id,
            "task_output_contract_id": self.task_output_contract_id,
            "final_artifact_alias": self.final_artifact_alias,
            "output_schema_id": self.output_schema_id,
            "assertions": assertions,
        }
        encoded = json.dumps(
            contract,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _invalid(detail: str) -> None:
        raise PydanticCustomError("t16_task_success_spec_invalid", detail)


class TaskSuccessSpecificationRegistry(StrictModel):
    """冻结 12 条件 evaluator 输入的版本化注册表。"""

    schema_version: Literal["0.1"] = "0.1"
    id: NonEmptyStr
    prompt_contract_id: NonEmptyStr
    artifact_schema_id: NonEmptyStr
    evaluator_id: NonEmptyStr
    evaluator_version: NonEmptyStr
    conditions: Annotated[
        tuple[TaskSuccessConditionSpecification, ...],
        Field(min_length=12, max_length=12),
    ]

    @model_validator(mode="after")
    def require_unique_condition_and_spec_ids(self) -> Self:
        """锁定唯一身份和统一 Artifact Schema。"""
        identities = (
            tuple(item.condition_id for item in self.conditions),
            tuple(item.spec_id for item in self.conditions),
        )
        if any(len(values) != len(set(values)) for values in identities):
            raise PydanticCustomError(
                "t16_task_success_registry_duplicate",
                "condition_id 与 spec_id 必须唯一",
            )
        if any(item.output_schema_id != self.artifact_schema_id for item in self.conditions):
            raise PydanticCustomError(
                "t16_task_success_schema_drift",
                "所有条件必须使用同一 v3 Artifact Schema",
            )
        return self
