"""确定性安全 Mock Harness。"""

from dataclasses import dataclass
from pathlib import Path

from skillflow.adapters.base import (
    HarnessSession,
    SkillBinding,
    SkillInvocation,
    SkillInvocationResult,
)
from skillflow.benchmark.scripted_backend import (
    ScriptedBackend,
    ScriptedInputArtifact,
    ScriptedInvocation,
)
from skillflow.instrumentation.context_proxy import InstrumentedContext
from skillflow.instrumentation.decision_stub import DecisionProvider
from skillflow.instrumentation.errors import HarnessStateError
from skillflow.instrumentation.file_proxy import InstrumentedFile
from skillflow.instrumentation.memory_proxy import InstrumentedMemory, MemoryState
from skillflow.instrumentation.mock_tools import (
    MockNetworkRecord,
    MockNetworkSink,
    MockShellRecord,
    MockShellSink,
    MockToolAdapter,
    MockToolServices,
)
from skillflow.instrumentation.skill_proxy import InstrumentedSkill, SkillState
from skillflow.instrumentation.tool_proxy import InstrumentedTool
from skillflow.models.authorization import AuthorizationGrant
from skillflow.models.enums import EventType, PrincipalType
from skillflow.runtime.session import (
    ActorCall,
    EventEmission,
    RuntimeDependencies,
    RuntimeRecorder,
    SessionIdentity,
)


@dataclass(frozen=True, slots=True)
class MockHarnessConfig:
    """Mock Harness 的固定 Run 依赖。"""

    run_id: str
    task_id: str
    workspace_root: Path
    dependencies: RuntimeDependencies
    initial_grants: tuple[AuthorizationGrant, ...] = ()


@dataclass(frozen=True, slots=True)
class _SessionRuntime:
    """只在一个活动 Session 中可访问的代理集合。"""

    recorder: RuntimeRecorder
    context: InstrumentedContext
    memory: InstrumentedMemory
    files: InstrumentedFile
    skills: InstrumentedSkill
    tools: InstrumentedTool


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
        self._runtime: _SessionRuntime | None = None
        self._initial_grants_registered = False

    def start_session(self, session: HarnessSession) -> None:
        """建立 Session 局部 Context/代理并保留 Run 级 Memory/Skill 状态。"""
        if self._runtime is not None:
            raise HarnessStateError("start_session", "session already active")
        recorder = RuntimeRecorder(
            SessionIdentity(
                run_id=self._config.run_id,
                task_id=self._config.task_id,
                session_id=session.session_id,
            ),
            self._config.dependencies,
        )
        files = InstrumentedFile(self._config.workspace_root, recorder)
        memory = InstrumentedMemory(recorder, self._memory_state)
        tools = InstrumentedTool(
            recorder,
            self._decisions,
            MockToolAdapter(
                MockToolServices(
                    files=files,
                    memory=memory,
                    network=self._network,
                    shell=self._shell,
                )
            ),
        )
        self._runtime = _SessionRuntime(
            recorder=recorder,
            context=InstrumentedContext(recorder),
            memory=memory,
            files=files,
            skills=InstrumentedSkill(recorder, self._skill_state),
            tools=tools,
        )
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

    def _require_runtime(self, operation: str) -> _SessionRuntime:
        if self._runtime is None:
            raise HarnessStateError(operation, "no active session")
        return self._runtime


class BenchmarkController:
    """不暴露给 Skill 的用户确认与撤销接口。"""

    def __init__(self, harness: MockHarnessAdapter) -> None:
        """绑定唯一 Harness，不向 ScriptedBackend 暴露该控制器。"""
        self._harness = harness

    def revoke_skill(self, skill_id: str, actor: PrincipalType) -> None:
        """仅允许 Benchmark 以可信主体撤销 Skill。"""
        self._require_trusted(actor, "revoke_skill")
        self._harness.benchmark_revoke_skill(skill_id, ActorCall(actor.value, None))

    def unload_skill(self, skill_id: str, actor: PrincipalType) -> None:
        """仅允许 Benchmark 以可信主体卸载 Skill。"""
        self._require_trusted(actor, "unload_skill")
        self._harness.benchmark_unload_skill(skill_id, ActorCall(actor.value, None))

    def confirm_tool(self, grant: AuthorizationGrant, actor: PrincipalType) -> None:
        """由 USER/TRUSTED_POLICY 特权确认生成结构化 Grant。"""
        self._require_trusted(actor, "confirm_tool")
        if grant.issuer_type is not actor:
            raise HarnessStateError("confirm_tool", "actor and issuer_type mismatch")
        self._harness.benchmark_issue_grant(grant, ActorCall(grant.issuer_id, None))

    def revoke_grant(self, grant_id: str, actor: PrincipalType) -> None:
        """由可信 Benchmark 主体撤销 Grant。"""
        self._require_trusted(actor, "revoke_grant")
        self._harness.benchmark_revoke_grant(grant_id, ActorCall(actor.value, None))

    @staticmethod
    def _require_trusted(actor: PrincipalType, operation: str) -> None:
        if actor not in {PrincipalType.USER, PrincipalType.TRUSTED_POLICY}:
            raise HarnessStateError(operation, f"untrusted actor: {actor.value}")
