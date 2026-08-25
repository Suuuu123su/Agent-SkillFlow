"""MockHarnessAdapter 的 checkpoint 存储编排。"""

from dataclasses import dataclass
from pathlib import Path

from skillflow.adapters.checkpoint import (
    HarnessCheckpoint,
    HarnessCheckpointParts,
    create_harness_checkpoint,
    verify_harness_checkpoint,
)
from skillflow.adapters.mock_session import MockSessionRuntime
from skillflow.instrumentation.errors import HarnessStateError
from skillflow.instrumentation.memory_proxy import MemoryState
from skillflow.instrumentation.mock_tools import MockNetworkSink, MockShellSink
from skillflow.instrumentation.skill_proxy import SkillState
from skillflow.runtime.determinism import DeterministicIdFactory, VirtualClock
from skillflow.runtime.session import RuntimeDependencies
from skillflow.runtime.workspace_checkpoint import capture_workspace, restore_workspace
from skillflow.store.checkpoint import (
    StoreCaptureRequest,
    StoreRestoreSetup,
    capture_run_store,
    restore_run_store,
)


@dataclass(frozen=True, slots=True)
class MockCheckpointCapture:
    """采集完整 Harness 状态所需的受控对象。"""

    run_id: str
    task_id: str
    workspace_root: Path
    dependencies: RuntimeDependencies
    runtime: MockSessionRuntime
    memory_state: MemoryState
    skill_state: SkillState
    network: MockNetworkSink
    shell: MockShellSink
    initial_grants_registered: bool


@dataclass(frozen=True, slots=True)
class MockCheckpointRestore:
    """把 checkpoint 导入新分支所需的受控对象。"""

    run_id: str
    task_id: str
    workspace_root: Path
    dependencies: RuntimeDependencies


def capture_mock_checkpoint(setup: MockCheckpointCapture) -> HarnessCheckpoint:
    """冻结全部内存态、Store、Blob 与 Workspace。"""
    clock, ids = checkpoint_determinism(setup.dependencies)
    memory = setup.memory_state.snapshot()
    store = capture_run_store(
        StoreCaptureRequest(
            setup.run_id,
            setup.dependencies.event_store,
            setup.dependencies.blob_store,
            memory.entries,
        )
    )
    return create_harness_checkpoint(
        HarnessCheckpointParts(
            source_run_id=setup.run_id,
            task_id=setup.task_id,
            session_id=setup.runtime.recorder.identity.session_id,
            provenance_mode=setup.dependencies.provenance_mode,
            store=store,
            workspace=capture_workspace(setup.workspace_root),
            context=setup.runtime.context.snapshot(),
            memory=memory,
            skill_state=setup.skill_state.snapshot(),
            skills=setup.runtime.skills.snapshot(),
            network_records=setup.network.records,
            shell_records=setup.shell.records,
            clock=clock.snapshot(),
            ids=ids.snapshot(),
            initial_grants_registered=setup.initial_grants_registered,
        )
    )


def restore_mock_checkpoint_storage(
    checkpoint: HarnessCheckpoint,
    setup: MockCheckpointRestore,
) -> None:
    """验证并逻辑导入分支持久层，再恢复时间与 ID。"""
    if checkpoint.task_id != setup.task_id:
        raise HarnessStateError("restore", "task_id mismatch")
    if checkpoint.provenance_mode is not setup.dependencies.provenance_mode:
        raise HarnessStateError("restore", "provenance mode mismatch")
    verify_harness_checkpoint(checkpoint)
    restore_workspace(checkpoint.workspace, setup.workspace_root)
    restore_run_store(
        checkpoint.store,
        StoreRestoreSetup(
            setup.run_id,
            setup.dependencies.event_store,
            setup.dependencies.blob_store,
        ),
    )
    clock, ids = checkpoint_determinism(setup.dependencies)
    clock.restore(checkpoint.clock)
    ids.restore(checkpoint.ids)


def checkpoint_determinism(
    dependencies: RuntimeDependencies,
) -> tuple[VirtualClock, DeterministicIdFactory]:
    """收窄为 T10 明确支持的可恢复确定性依赖。"""
    clock = dependencies.clock
    ids = dependencies.id_factory
    if not isinstance(clock, VirtualClock) or not isinstance(ids, DeterministicIdFactory):
        raise HarnessStateError("checkpoint", "dependencies are not checkpointable")
    return clock, ids
