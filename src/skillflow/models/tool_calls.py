"""Mock Tool 请求使用的中立封闭数据合同。"""

from enum import StrEnum, unique
from typing import Annotated, Literal, TypeAlias

from pydantic import Field, StringConstraints

from skillflow.models.base import NonEmptyStr, StrictModel
from skillflow.models.resources import ResourceRef

MemoryKey = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")]


@unique
class MockToolName(StrEnum):
    """安全 Mock Tool 白名单。"""

    READ_FILE = "read_file"
    WRITE_MEMORY = "write_memory"
    READ_MEMORY = "read_memory"
    HTTP_SEND = "http_send"
    SHELL_EXEC = "shell_exec"


class ReadFileArgs(StrictModel):
    """read_file 参数。"""

    kind: Literal[MockToolName.READ_FILE] = MockToolName.READ_FILE
    resource: ResourceRef
    sink: ResourceRef = ResourceRef("context:/task")
    sensitivity: Annotated[int, Field(ge=0, le=4)] = 0


class WriteMemoryArgs(StrictModel):
    """write_memory 参数。"""

    kind: Literal[MockToolName.WRITE_MEMORY] = MockToolName.WRITE_MEMORY
    key: MemoryKey
    source_artifact_id: NonEmptyStr
    source: ResourceRef
    sensitivity: Annotated[int, Field(ge=0, le=4)] = 0


class ReadMemoryArgs(StrictModel):
    """read_memory 参数。"""

    kind: Literal[MockToolName.READ_MEMORY] = MockToolName.READ_MEMORY
    key: MemoryKey
    sink: ResourceRef = ResourceRef("context:/task")
    sensitivity: Annotated[int, Field(ge=0, le=4)] = 0


class HttpSendArgs(StrictModel):
    """http_send 参数。"""

    kind: Literal[MockToolName.HTTP_SEND] = MockToolName.HTTP_SEND
    source_artifact_id: NonEmptyStr
    source: ResourceRef
    sink: ResourceRef
    sensitivity: Annotated[int, Field(ge=0, le=4)] = 0


class ShellExecArgs(StrictModel):
    """shell_exec 参数。"""

    kind: Literal[MockToolName.SHELL_EXEC] = MockToolName.SHELL_EXEC
    command: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
    sink: ResourceRef = ResourceRef("mock://shell")
    sensitivity: Annotated[int, Field(ge=0, le=4)] = 0


ToolArguments: TypeAlias = (
    ReadFileArgs | WriteMemoryArgs | ReadMemoryArgs | HttpSendArgs | ShellExecArgs
)


class ToolCallRequest(StrictModel):
    """一次带稳定脚本动作 ID 的类型化 Tool 请求。"""

    actor_id: NonEmptyStr
    call_id: NonEmptyStr
    action_id: NonEmptyStr
    decision_key: NonEmptyStr
    arguments: ToolArguments


class ToolActionAttempt(StrictModel):
    """一次脚本动作已产生 Tool argument 的中立运行证据。"""

    action_id: NonEmptyStr
    actor_id: NonEmptyStr
    call_id: NonEmptyStr
    tool: MockToolName
    argument_artifact_id: NonEmptyStr
    executed: bool
