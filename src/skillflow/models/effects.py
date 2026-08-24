"""能力申请与实际效果记录。"""

from typing import Annotated, Self

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.enums import CapabilityAction, Lifetime
from skillflow.models.resources import ResourceRef


class CapabilityEffect(StrictModel):
    """可比较的结构化能力效果。"""

    source: ResourceRef | None
    action: CapabilityAction
    sink: ResourceRef
    scope: NonEmptyStr
    lifetime: Lifetime
    sensitivity: Annotated[int, Field(ge=0, le=4)]


class EffectRecord(StrictModel):
    """一次运行中的效果请求与执行结果。"""

    effect_id: NonEmptyStr
    effect_alias: NonEmptyStr | None = None
    effect: CapabilityEffect
    request_event_id: NonEmptyStr
    decision_id: NonEmptyStr
    result_event_id: NonEmptyStr | None = None
    tool_receipt_id: NonEmptyStr | None = None
    executed: bool

    @model_validator(mode="after")
    def require_execution_evidence(self) -> Self:
        """已执行效果必须同时引用结果事件和 Tool Receipt。"""
        if self.executed and (self.result_event_id is None or self.tool_receipt_id is None):
            raise PydanticCustomError(
                "effect_execution_evidence_missing",
                "executed EffectRecord 要求 result_event_id 和 tool_receipt_id",
            )
        return self
