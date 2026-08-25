"""确定性安全 Mock Harness。"""

from dataclasses import dataclass
from pathlib import Path

from skillflow.adapters.base import (
    HarnessSession,
    SkillBinding,
    SkillInvocation,
    SkillInvocationResult,
)
from skillflow.adapters.benchmark_controller import BenchmarkController
from skillflow.adapters.checkpoint import (
    HarnessCheckpoint,
)
from skillflow.adapters.mock_checkpoint import (
    MockCheckpointCapture,
    MockCheckpointRestore,
    capture_mock_checkpoint,
    restore_mock_checkpoint_storage,
)
from skillflow.adapters.mock_session import (
    MockSessionRuntime,
    MockSessionSetup,
    create_mock_session,
)
from skillflow.benchmark.scripted_backend import (
    ScriptedBackend,
    ScriptedInputArtifact,
    ScriptedInvocation,
)
from skillflow.instrumentation.decision_stub import DecisionProvider
from skillflow.instrumentation.errors import HarnessStateError
from skillflow.instrumentation.memory_proxy import MemoryState
from skillflow.instrumentation.mock_tools import (
    MockNetworkRecord,
    MockNetworkSink,
    MockShellRecord,
    MockShellSink,
)
from skillflow.instrumentation.skill_proxy import SkillState
from skillflow.models.authorization import AuthorizationGrant
from skillflow.models.enums import EventType
from skillflow.models.provenance import Artifact
from skillflow.runtime.session import (
    ActorCall,
    EventEmission,
    RuntimeDependencies,
    SessionIdentity,
)

__all__ = (
    "BenchmarkController",
    "MockHarnessAdapter",
    "MockHarnessConfig",
)


@dataclass(frozen=True, slots=True)
class MockHarnessConfig:
    """Mock Harness 的固定 Run 依赖。"""

    run_id: str
    task_id: str
    workspace_root: Path
    dependencies: RuntimeDependencies
    initial_grants: tuple[AuthorizationGrant, ...] = ()


class MockHarnessAdapter:
    """不访问真实 LLM、网络或 Shell 的 Harness。"""

    def __init__(
        self,
        config: MockHarnessConfig,
        backend: ScriptedBackend,
        decisions: DecisionProvider,
    ) -> None:
        """建立一个全新的 Run 级隔离状态。"""
        self._config = config
        self._backend = backend
        self._decisions = decisions
        self._memory_state = MemoryState()
        self._skill_state = SkillState()
        self._network = MockNetworkSink()
        self._shell = MockShellSink()
        self._runtime: MockSessionRuntime | None = None
        self._initial_grants_registered = False

    def start_session(self, session: HarnessSession) -> None:
        """建立 Session 局部 Context/代理并保留 Run 级 Memory/Skill 状态。"""
        if self._runtime is not None:
            raise HarnessStateError("start_session", "session already active")
        self._runtime = self._create_runtime(session)
        recorder = self._runtime.recorder
        recorder.record_event(
            EventEmission(event_type=EventType.SESSION_START, actor=ActorCall("harness", None))
        )
        if not self._initial_grants_registered:
            for grant in self._config.initial_grants:
                recorder.record_authorization_grant(
                    grant,
                    ActorCall(grant.issuer_id, None),
                )
            self._initial_grants_registered = True

    def _create_runtime(self, session: HarnessSession) -> MockSessionRuntime:
        """构造 Session 代理；是否追加生命周期 Event 由调用方决定。"""
        return create_mock_session(
            MockSessionSetup(
                identity=SessionIdentity(
                    run_id=self._config.run_id,
                    task_id=self._config.task_id,
                    session_id=session.session_id,
                ),
                dependencies=self._config.dependencies,
                workspace_root=self._config.workspace_root,
                decisions=self._decisions,
                memory_state=self._memory_state,
                skill_state=self._skill_state,
                network=self._network,
                shell=self._shell,
            )
        )

    def load_skill(self, binding: SkillBinding) -> None:
        """首次加载时安装固定绑定，再加载到当前 Session。"""
        runtime = self._require_runtime("load_skill")
        actor = ActorCall("harness", None)
        if not self._skill_state.is_installed(binding.skill_id):
            runtime.skills.install(binding, actor)
        runtime.skills.load(binding.skill_id, actor)

    def invoke_skill(self, invocation: SkillInvocation) -> SkillInvocationResult:
        """通过 Scripted Backend 执行一次显式 Skill 调用。"""
        runtime = self._require_runtime("invoke_skill")
        binding = runtime.skills.binding(invocation.skill_id)
        actor = ActorCall(invocation.skill_id, runtime.recorder.new_id("call"))
        token = runtime.skills.invoke(
            invocation.skill_id,
            invocation.input_artifact_ids,
            actor,
        )
        inputs = tuple(
            ScriptedInputArtifact(
                artifact_id=artifact_id,
                content_hash=artifact.content_hash,
                content_length=artifact.content_length,
            )
            for artifact_id in invocation.input_artifact_ids
            for artifact in (runtime.recorder.require_artifact(artifact_id),)
        )
        scripted = self._backend.invoke(
            ScriptedInvocation(binding.implementation, actor, runtime.tools, inputs)
        )
        parents = tuple(
            dict.fromkeys((*invocation.input_artifact_ids, *scripted.parent_artifact_ids))
        )
        output = runtime.skills.return_output(token, scripted.output, parents)
        if actor.call_id is None:
            raise HarnessStateError("invoke_skill", "call_id missing")
        return SkillInvocationResult(
            output=output,
            receipts=scripted.receipts,
            attempts=scripted.attempts,
            call_id=actor.call_id,
            input_artifact_ids=invocation.input_artifact_ids,
        )

    def end_session(self) -> None:
        """显式卸载剩余 Skill、记录结束并丢弃 Session 局部代理。"""
        runtime = self._require_runtime("end_session")
        actor = ActorCall("harness", None)
        for skill_id in runtime.skills.loaded_skill_ids:
            runtime.skills.unload(skill_id, actor)
        runtime.recorder.record_event(EventEmission(event_type=EventType.SESSION_END, actor=actor))
        self._runtime = None

    def checkpoint(self) -> HarnessCheckpoint:
        """在活动 Session 的静止 step 边界冻结完整状态。"""
        return capture_mock_checkpoint(
            MockCheckpointCapture(
                self._config.run_id,
                self._config.task_id,
                self._config.workspace_root,
                self._config.dependencies,
                self._require_runtime("checkpoint"),
                self._memory_state,
                self._skill_state,
                self._network,
                self._shell,
                self._initial_grants_registered,
            )
        )

    def restore(self, checkpoint: HarnessCheckpoint) -> None:
        """逻辑导入到当前全新分支，不重放 Session/Grant 生命周期。"""
        if self._runtime is not None:
            raise HarnessStateError("restore", "target session already active")
        restore_mock_checkpoint_storage(
            checkpoint,
            MockCheckpointRestore(
                self._config.run_id,
                self._config.task_id,
                self._config.workspace_root,
                self._config.dependencies,
            ),
        )
        self._memory_state.restore(checkpoint.memory)
        self._skill_state.restore(checkpoint.skill_state)
        self._network.restore(checkpoint.network_records)
        self._shell.restore(checkpoint.shell_records)
        self._initial_grants_registered = checkpoint.initial_grants_registered
        self._runtime = self._create_runtime(HarnessSession(checkpoint.session_id))
        self._runtime.context.restore(checkpoint.context)
        self._runtime.skills.restore(checkpoint.skills)
        restored = self.checkpoint()
        if (
            restored.prefix_hash != checkpoint.prefix_hash
            or restored.state_hash != checkpoint.state_hash
        ):
            raise HarnessStateError("restore", "restored state hash mismatch")

    @property
    def network_records(self) -> tuple[MockNetworkRecord, ...]:
        """返回当前 Run 的内存网络记录。"""
        return self._network.records

    @property
    def shell_records(self) -> tuple[MockShellRecord, ...]:
        """返回当前 Run 的内存 Shell 记录。"""
        return self._shell.records

    def benchmark_revoke_skill(self, skill_id: str, actor: ActorCall) -> None:
        """仅供 BenchmarkController 调用的撤销入口。"""
        runtime = self._require_runtime("revoke_skill")
        runtime.skills.revoke(skill_id, actor)

    def benchmark_add_context(self, content: bytes, actor: ActorCall) -> Artifact:
        """仅供 BenchmarkController 建立受控 Context 前缀。"""
        return self._require_runtime("add_context").context.add(content, actor)

    def benchmark_write_memory(
        self,
        key: str,
        source_artifact_id: str,
        actor: ActorCall,
    ) -> Artifact:
        """仅供 BenchmarkController 建立受控 Memory 前缀。"""
        return self._require_runtime("write_memory").memory.write(
            key,
            source_artifact_id,
            actor,
        )

    def benchmark_unload_skill(self, skill_id: str, actor: ActorCall) -> None:
        """仅供 BenchmarkController 调用的卸载入口。"""
        runtime = self._require_runtime("unload_skill")
        runtime.skills.unload(skill_id, actor)

    def benchmark_issue_grant(self, grant: AuthorizationGrant, actor: ActorCall) -> None:
        """仅供 BenchmarkController 调用的结构化确认入口。"""
        runtime = self._require_runtime("confirm_tool")
        runtime.recorder.record_authorization_grant(grant, actor)

    def benchmark_revoke_grant(self, grant_id: str, actor: ActorCall) -> None:
        """仅供 BenchmarkController 调用的 Grant 撤销入口。"""
        runtime = self._require_runtime("revoke_grant")
        runtime.recorder.record_authorization_revocation(grant_id, actor)

    def _require_runtime(self, operation: str) -> MockSessionRuntime:
        if self._runtime is None:
            raise HarnessStateError(operation, "no active session")
        return self._runtime
