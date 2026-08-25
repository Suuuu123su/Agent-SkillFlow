"""封闭 Mock Tool 参数到 CapabilityEffect 的机械规范化。"""

from dataclasses import dataclass
from typing import assert_never

from skillflow.instrumentation.tool_types import (
    HttpSendArgs,
    ReadFileArgs,
    ReadMemoryArgs,
    ShellExecArgs,
    ToolArguments,
    WriteMemoryArgs,
)
from skillflow.models.effects import CapabilityEffect
from skillflow.models.enums import CapabilityAction, Lifetime, Scope
from skillflow.models.resources import ResourceRef


@dataclass(frozen=True, slots=True)
class NormalizedToolRequest:
    """白名单参数规范化后的 Effect 与父 Artifact。"""

    effect: CapabilityEffect
    source_artifact_ids: tuple[str, ...]


def normalize_tool_request(arguments: ToolArguments) -> NormalizedToolRequest:
    """把封闭 Tool 参数机械规范化为 CapabilityEffect。"""
    source: ResourceRef | None
    sink: ResourceRef
    source_ids: tuple[str, ...]
    match arguments:
        case ReadFileArgs(resource=resource, sink=sink, sensitivity=sensitivity):
            action = CapabilityAction.FILE_READ
            source = resource
            scope = Scope.EXACT_FILE
            source_ids = ()
        case WriteMemoryArgs(
            key=key,
            source_artifact_id=source_id,
            source=source,
            sensitivity=sensitivity,
        ):
            action = CapabilityAction.MEMORY_WRITE
            sink = ResourceRef(f"memory:/{key}")
            scope = Scope.EXACT_KEY
            source_ids = (source_id,)
        case ReadMemoryArgs(key=key, sink=sink, sensitivity=sensitivity):
            action = CapabilityAction.MEMORY_READ
            source = ResourceRef(f"memory:/{key}")
            scope = Scope.EXACT_KEY
            source_ids = ()
        case HttpSendArgs(
            source_artifact_id=source_id,
            source=source,
            sink=sink,
            sensitivity=sensitivity,
        ):
            action = CapabilityAction.NETWORK_SEND
            scope = Scope.EXACT_SINK
            source_ids = (source_id,)
        case ShellExecArgs(sink=sink, sensitivity=sensitivity):
            action = CapabilityAction.SHELL_EXECUTE
            source = None
            scope = Scope.COMMAND
            source_ids = ()
        case _ as unreachable:
            assert_never(unreachable)
    return NormalizedToolRequest(
        effect=CapabilityEffect(
            source=source,
            action=action,
            sink=sink,
            scope=scope,
            lifetime=Lifetime.CALL,
            sensitivity=sensitivity,
        ),
        source_artifact_ids=source_ids,
    )
