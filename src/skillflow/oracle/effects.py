"""从中立 Tool 参数独立规范化 Oracle Effect。"""

from dataclasses import dataclass
from typing import assert_never

from skillflow.models.effects import CapabilityEffect
from skillflow.models.enums import CapabilityAction, Lifetime
from skillflow.models.resources import ResourceRef
from skillflow.models.tool_calls import (
    HttpSendArgs,
    ReadFileArgs,
    ReadMemoryArgs,
    ShellExecArgs,
    ToolArguments,
    WriteMemoryArgs,
)


@dataclass(frozen=True, slots=True)
class OracleActionSemantics:
    """Oracle 独立解释得到的 Effect 与数据父值。"""

    effect: CapabilityEffect
    source_artifact_ids: tuple[str, ...]


def oracle_action_semantics(arguments: ToolArguments) -> OracleActionSemantics:
    """不调用 Observed ToolProxy 的规范化逻辑。"""
    source: ResourceRef | None
    sink: ResourceRef
    source_ids: tuple[str, ...]
    match arguments:
        case ReadFileArgs(resource=resource, sink=sink, sensitivity=sensitivity):
            action = CapabilityAction.FILE_READ
            source = resource
            scope = "exact-file"
            source_ids = ()
        case WriteMemoryArgs(
            key=key,
            source_artifact_id=source_id,
            source=source,
            sensitivity=sensitivity,
        ):
            action = CapabilityAction.MEMORY_WRITE
            sink = ResourceRef(f"memory:/{key}")
            scope = "exact-key"
            source_ids = (source_id,)
        case ReadMemoryArgs(key=key, sink=sink, sensitivity=sensitivity):
            action = CapabilityAction.MEMORY_READ
            source = ResourceRef(f"memory:/{key}")
            scope = "exact-key"
            source_ids = ()
        case HttpSendArgs(
            source_artifact_id=source_id,
            source=source,
            sink=sink,
            sensitivity=sensitivity,
        ):
            action = CapabilityAction.NETWORK_SEND
            scope = "exact-sink"
            source_ids = (source_id,)
        case ShellExecArgs(sink=sink, sensitivity=sensitivity):
            action = CapabilityAction.SHELL_EXECUTE
            source = None
            scope = "command"
            source_ids = ()
        case _ as unreachable:
            assert_never(unreachable)
    return OracleActionSemantics(
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
