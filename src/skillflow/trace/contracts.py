"""双轨 Trace 共用的稳定 ID 与父关系合同。"""

from enum import StrEnum, unique

from skillflow.models.base import NonEmptyStr, StrictModel


@unique
class ParentRelation(StrEnum):
    """T06 固定记录的值与效果父关系。"""

    COPY = "copy"
    DERIVE = "derive"
    WRITE = "write"
    LOAD = "load"
    INVOKE = "invoke"


@unique
class TraceValueType(StrEnum):
    """可进入双轨 Trace 的值类别。"""

    ASSET = "asset"
    CONTEXT = "context"
    MEMORY = "memory"
    FILE = "file"
    SKILL_OUTPUT = "skill_output"
    TOOL_ARG = "tool_arg"
    TOOL_RETURN = "tool_return"


class TraceParent(StrictModel):
    """一个稳定父 ID 及其机械关系。"""

    parent_id: NonEmptyStr
    relation: ParentRelation
