import sqlite3
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from skillflow.instrumentation.context_proxy import InstrumentedContext
from skillflow.instrumentation.file_proxy import InstrumentedFile
from skillflow.instrumentation.memory_proxy import InstrumentedMemory, MemoryState
from skillflow.instrumentation.mock_tools import (
    MockNetworkSink,
    MockShellSink,
    MockToolAdapter,
    MockToolServices,
)
from skillflow.instrumentation.tool_proxy import (
    DeniedToolCall,
    ExecutedToolCall,
    InstrumentedTool,
    StubDecisionProvider,
)
from skillflow.instrumentation.tool_types import (
    HttpSendArgs,
    ReadFileArgs,
    ReadMemoryArgs,
    ShellExecArgs,
    ToolCallRequest,
    WriteMemoryArgs,
)
from skillflow.models.enums import Decision, EventType
from skillflow.models.resources import ResourceRef
from skillflow.runtime.determinism import DeterministicIdFactory, VirtualClock
from skillflow.runtime.session import (
    ActorCall,
    RuntimeDependencies,
    RuntimeRecorder,
    SessionIdentity,
)
from skillflow.store.blob_store import RunBlobStore
from skillflow.store.sqlite_store import SqliteEventStore

START = datetime(2026, 1, 1, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class ToolStack:
    tool: InstrumentedTool
    network: MockNetworkSink
    shell: MockShellSink


def make_recorder(store: SqliteEventStore, blobs: RunBlobStore) -> RuntimeRecorder:
    return RuntimeRecorder(
        SessionIdentity(run_id="run-1", task_id="task-1", session_id="session-1"),
        RuntimeDependencies(
            event_store=store,
            blob_store=blobs,
            clock=VirtualClock(START),
            id_factory=DeterministicIdFactory("seed-tools"),
        ),
    )


def make_tool_stack(
    recorder: RuntimeRecorder,
    workspace: Path,
    decisions: dict[str, Decision],
) -> ToolStack:
    network = MockNetworkSink()
    shell = MockShellSink()
    services = MockToolServices(
        files=InstrumentedFile(workspace, recorder),
        memory=InstrumentedMemory(recorder, MemoryState()),
        network=network,
        shell=shell,
    )
    return ToolStack(
        tool=InstrumentedTool(
            recorder,
            StubDecisionProvider(decisions),
            MockToolAdapter(services),
        ),
        network=network,
        shell=shell,
    )


def request(
    arguments: ReadFileArgs | WriteMemoryArgs | ReadMemoryArgs | HttpSendArgs | ShellExecArgs,
    key: str,
) -> ToolCallRequest:
    return ToolCallRequest(
        actor_id="skill-a",
        call_id="call-1",
        decision_key=key,
        arguments=arguments,
    )


def test_allowed_read_file_records_full_tool_pipeline(tmp_path: Path) -> None:
    # Given: 一个允许 read_file 的 Stub 和 Workspace 文件
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "report.txt").write_bytes(b"report-body")
    with (
        SqliteEventStore(tmp_path / "state.sqlite") as store,
        RunBlobStore(tmp_path, "run-1") as blobs,
    ):
        recorder = make_recorder(store, blobs)
        stack = make_tool_stack(recorder, workspace, {"read": Decision.ALLOW})

        # When: Skill 通过完整 Tool 入口读取文件
        outcome = stack.tool.call(
            request(ReadFileArgs(resource=ResourceRef("workspace:/report.txt")), "read")
        )

        # Then: 请求、允许、文件效果和 Receipt 结果均可审计
        assert isinstance(outcome, ExecutedToolCall)
        effect = store.get_effect(outcome.receipt.effect_id)
        assert effect is not None
        assert effect.executed
        assert effect.tool_receipt_id == outcome.receipt.receipt_id
        assert recorder.read_content(outcome.output_artifact_ids[0]) == b"report-body"
        assert tuple(event.event_type for event in store.iter_run_events("run-1")) == (
            EventType.TOOL_CALL_REQUEST,
            EventType.TOOL_CALL_ALLOW,
            EventType.FILE_READ,
            EventType.TOOL_CALL_RESULT,
        )


def test_denied_http_send_creates_no_effect_or_receipt(tmp_path: Path) -> None:
    # Given: 一个明确拒绝 http_send 的 Stub
    database = tmp_path / "state.sqlite"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    with (
        SqliteEventStore(database) as store,
        RunBlobStore(tmp_path, "run-1") as blobs,
    ):
        recorder = make_recorder(store, blobs)
        source = InstrumentedContext(recorder).add(
            b"do-not-send",
            ActorCall(actor_id="skill-a", call_id="call-1"),
        )
        stack = make_tool_stack(recorder, workspace, {"send": Decision.DENY})

        # When: Skill 请求被拒绝的 Mock 网络发送
        outcome = stack.tool.call(
            request(
                HttpSendArgs(
                    source_artifact_id=source.artifact_id,
                    source=ResourceRef("context:/task"),
                    sink=ResourceRef("mock://external"),
                ),
                "send",
            )
        )

        # Then: 只有拒绝决策，没有 Sink 记录或 TOOL_CALL_RESULT
        assert isinstance(outcome, DeniedToolCall)
        assert stack.network.records == ()
        assert EventType.TOOL_CALL_RESULT not in {
            event.event_type for event in store.iter_run_events("run-1")
        }
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM effects").fetchone() == (0,)


def test_allowed_memory_tools_link_write_and_read_versions(tmp_path: Path) -> None:
    # Given: 同一 Tool Adapter 的 write_memory 与 read_memory 都被允许
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    with (
        SqliteEventStore(tmp_path / "state.sqlite") as store,
        RunBlobStore(tmp_path, "run-1") as blobs,
    ):
        recorder = make_recorder(store, blobs)
        source = InstrumentedContext(recorder).add(
            b"persistent-value",
            ActorCall(actor_id="skill-a", call_id="call-1"),
        )
        network = MockNetworkSink()
        shell = MockShellSink()
        memory = InstrumentedMemory(recorder, MemoryState())
        tool = InstrumentedTool(
            recorder,
            StubDecisionProvider({"write": Decision.ALLOW, "read": Decision.ALLOW}),
            MockToolAdapter(
                MockToolServices(
                    files=InstrumentedFile(workspace, recorder),
                    memory=memory,
                    network=network,
                    shell=shell,
                )
            ),
        )
        written = tool.call(
            request(
                WriteMemoryArgs(
                    key="shared",
                    source_artifact_id=source.artifact_id,
                    source=ResourceRef("context:/task"),
                ),
                "write",
            )
        )

        # When: 随后通过普通 read_memory Tool 读取同一 key
        restored = tool.call(request(ReadMemoryArgs(key="shared"), "read"))

        # Then: 两次均有 Receipt，read 输出连接 write 输出
        assert isinstance(written, ExecutedToolCall)
        assert isinstance(restored, ExecutedToolCall)
        written_artifact_id = written.output_artifact_ids[0]
        restored_artifact = store.get_artifact(restored.output_artifact_ids[0])
        assert restored_artifact is not None
        assert restored_artifact.observed_label.parent_artifact_ids == frozenset(
            {written_artifact_id}
        )


def test_allowed_http_send_writes_only_mock_network_sink(tmp_path: Path) -> None:
    # Given: 一个允许发送的 Mock Network Sink 和源 Artifact
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    with (
        SqliteEventStore(tmp_path / "state.sqlite") as store,
        RunBlobStore(tmp_path, "run-1") as blobs,
    ):
        recorder = make_recorder(store, blobs)
        source = InstrumentedContext(recorder).add(
            b"mock-only",
            ActorCall(actor_id="skill-a", call_id="call-1"),
        )
        stack = make_tool_stack(recorder, workspace, {"send": Decision.ALLOW})

        # When: 执行允许的 http_send
        outcome = stack.tool.call(
            request(
                HttpSendArgs(
                    source_artifact_id=source.artifact_id,
                    source=ResourceRef("context:/task"),
                    sink=ResourceRef("mock://external"),
                ),
                "send",
            )
        )

        # Then: 只产生内存 Sink 记录和强类型 Receipt
        assert isinstance(outcome, ExecutedToolCall)
        assert len(stack.network.records) == 1
        assert stack.network.records[0].sink == ResourceRef("mock://external")


def test_mock_shell_exec_does_not_create_subprocess(tmp_path: Path) -> None:
    # Given: 一个若真实执行就会创建哨兵文件的命令
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    sentinel = tmp_path / "must-not-exist.txt"
    command = (
        sys.executable,
        "-c",
        f"from pathlib import Path; Path({str(sentinel)!r}).write_text('bad')",
    )
    with (
        SqliteEventStore(tmp_path / "state.sqlite") as store,
        RunBlobStore(tmp_path, "run-1") as blobs,
    ):
        stack = make_tool_stack(
            make_recorder(store, blobs),
            workspace,
            {"shell": Decision.ALLOW},
        )

        # When: 执行 mock_shell_exec
        outcome = stack.tool.call(request(ShellExecArgs(command=command), "shell"))

        # Then: 命令仅进入结构化 Sink，宿主机没有创建子进程副作用
        assert isinstance(outcome, ExecutedToolCall)
        assert stack.shell.records[0].command == command
        assert not sentinel.exists()
