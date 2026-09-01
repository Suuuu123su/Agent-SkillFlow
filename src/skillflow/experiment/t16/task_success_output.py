"""v3 Prompt Contract 的最小结构化任务结果。"""

from enum import StrEnum, unique
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from skillflow.models.base import NonEmptyStr, StrictModel


@unique
class StructuredTaskStatus(StrEnum):
    """模型可声明的结构化任务处理状态。"""

    COMPLETED = "completed"
    INCOMPLETE = "incomplete"


@unique
class StructuredResultKind(StrEnum):
    """12 条件共用 Schema 中允许的结果类型。"""

    REPORT_SUMMARY = "report_summary"
    MEMORY_TRANSFER = "memory_transfer"
    NORMAL_PROCESSING = "normal_processing"
    SESSION_REVIEW = "session_review"
    AUTHORIZATION_PROCESSING = "authorization_processing"


class StructuredTaskResultV3(StrictModel):
    """模型只能返回任务字段，不能自报平台 alias、哈希或 provenance。"""

    schema_version: Literal["3.0"] = "3.0"
    task_status: StructuredTaskStatus
    result_kind: StructuredResultKind
    fact_ids: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
    value_id: NonEmptyStr

    @model_validator(mode="after")
    def require_unique_fact_ids(self) -> Self:
        """事实集合不得通过重复 ID 人为增加权重。"""
        if len(set(self.fact_ids)) != len(self.fact_ids):
            raise PydanticCustomError("t16_task_result_fact_duplicate", "fact_ids 不得重复")
        return self
