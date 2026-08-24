"""无真实外部副作用的 Mock Tool Adapter。"""

from dataclasses import dataclass
from datetime import datetime
from typing import assert_never

from skillflow.instrumentation.file_proxy import InstrumentedFile
from skillflow.instrumentation.memory_proxy import InstrumentedMemory
from skillflow.instrumentation.tool_receipt import (
    ToolReceipt,
    ToolReceiptDraft,
    ToolReceiptIssuer,
)
from skillflow.instrumentation.tool_types import (
    HttpSendArgs,
    ReadFileArgs,
    ReadMemoryArgs,
    ShellExecArgs,
    ToolArguments,
    WriteMemoryArgs,
)
from skillflow.models.resources import ResourceRef
from skillflow.runtime.session import ActorCall


@dataclass(frozen=True, slots=True)
class MockToolServices:
    """Mock Tool Adapter 可访问的四个安全执行边界。"""

    files: InstrumentedFile
    memory: InstrumentedMemory
    network: "MockNetworkSink"
    shell: "MockShellSink"


@dataclass(frozen=True, slots=True)
class MockNetworkRecord:
    """一次未离开进程的结构化网络发送记录。"""

    effect_id: str
    sink: ResourceRef
    source_artifact_id: str


class MockNetworkSink:
    """只保留结构化发送记录的内存 Sink。"""

    def __init__(self) -> None:
        """Sink 的职责就是累积当前 Run 的 Mock 记录。"""
        self._records: list[MockNetworkRecord] = []

    @property
    def records(self) -> tuple[MockNetworkRecord, ...]:
        """返回不可变记录视图。"""
        return tuple(self._records)

    def send(self, effect_id: str, sink: ResourceRef, source_artifact_id: str) -> None:
        """只追加记录，不建立网络连接。"""
        self._records.append(MockNetworkRecord(effect_id, sink, source_artifact_id))


@dataclass(frozen=True, slots=True)
class MockShellRecord:
    """一次未执行的结构化 Shell 命令记录。"""

    effect_id: str
    command: tuple[str, ...]


class MockShellSink:
    """只保留结构化命令记录且不创建子进程。"""

    def __init__(self) -> None:
        """Sink 的职责就是累积当前 Run 的 Mock 命令。"""
        self._records: list[MockShellRecord] = []

    @property
    def records(self) -> tuple[MockShellRecord, ...]:
        """返回不可变记录视图。"""
        return tuple(self._records)

    def execute(self, effect_id: str, command: tuple[str, ...]) -> None:
        """只追加记录，不调用 subprocess、Shell 或 OS 执行接口。"""
        self._records.append(MockShellRecord(effect_id, command))


@dataclass(frozen=True, slots=True)
class MockExecutionRequest:
    """Mock Tool 执行与 Receipt 签发所需的完整事实。"""

    arguments: ToolArguments
    actor: ActorCall
    effect_id: str
    request_event_id: str
    result_event_id: str
    decision_id: str
    receipt_id: str
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class MockExecutionResult:
    """Mock Tool 已执行后的数据输出与 Receipt。"""

    receipt: ToolReceipt
    output_artifact_ids: tuple[str, ...]


class MockToolAdapter:
    """执行受控 File/Memory/Network/Shell 操作并签发 Receipt。"""

    def __init__(self, services: MockToolServices) -> None:
        """绑定受控服务并独占 Receipt 签发器。"""
        self._services = services
        self._issuer = ToolReceiptIssuer()

    def execute(self, request: MockExecutionRequest) -> MockExecutionResult:
        """执行一个已允许的白名单动作，不接触真实网络或 Shell。"""
        arguments = request.arguments
        output_ids: tuple[str, ...]
        match arguments:
            case ReadFileArgs(resource=resource):
                artifact = self._services.files.read(resource, request.actor)
                output_ids = (artifact.artifact_id,)
            case WriteMemoryArgs(key=key, source_artifact_id=source_id):
                artifact = self._services.memory.write(key, source_id, request.actor)
                output_ids = (artifact.artifact_id,)
            case ReadMemoryArgs(key=key):
                artifact = self._services.memory.read(key, request.actor)
                output_ids = (artifact.artifact_id,)
            case HttpSendArgs(sink=sink, source_artifact_id=source_id):
                self._services.network.send(request.effect_id, sink, source_id)
                output_ids = ()
            case ShellExecArgs(command=command):
                self._services.shell.execute(request.effect_id, command)
                output_ids = ()
            case _ as unreachable:
                assert_never(unreachable)
        receipt = self._issuer.issue(
            ToolReceiptDraft(
                receipt_id=request.receipt_id,
                tool=arguments.kind,
                effect_id=request.effect_id,
                request_event_id=request.request_event_id,
                result_event_id=request.result_event_id,
                decision_id=request.decision_id,
                actor_id=request.actor.actor_id,
                timestamp=request.timestamp,
                output_artifact_ids=output_ids,
            )
        )
        return MockExecutionResult(receipt=receipt, output_artifact_ids=output_ids)
