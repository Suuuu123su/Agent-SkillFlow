"""Skill 生命周期插桩。"""

from dataclasses import dataclass

from skillflow.adapters.base import SkillBinding
from skillflow.instrumentation.errors import SkillLifecycleError
from skillflow.models.enums import ArtifactType, EventType, TrustLevel
from skillflow.models.provenance import Artifact
from skillflow.runtime.session import (
    ActorCall,
    ArtifactEmission,
    EventEmission,
    RuntimeRecorder,
)


@dataclass(frozen=True, slots=True)
class SkillInvocationToken:
    """一次已记录、尚未 return 的 Skill 调用。"""

    skill_id: str
    actor: ActorCall
    input_artifact_ids: tuple[str, ...]
    invocation_event_id: str


@dataclass(frozen=True, slots=True)
class SkillStateSnapshot:
    """Run 级安装绑定与撤销集合。"""

    bindings: tuple[SkillBinding, ...]
    revoked_skill_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SkillRuntimeSnapshot:
    """Session 级加载与活动调用集合。"""

    loaded_skill_ids: tuple[str, ...]
    active_invocation_event_ids: tuple[str, ...]


class SkillState:
    """一个 Run 内跨 Session 持续存在的安装与撤销状态。"""

    def __init__(self) -> None:
        """初始化空的安装 registry 和撤销集合。"""
        self._bindings: dict[str, SkillBinding] = {}
        self._revoked: set[str] = set()

    def register(self, binding: SkillBinding) -> None:
        """注册一次全新安装。"""
        if binding.skill_id in self._bindings:
            raise SkillLifecycleError(binding.skill_id, "install", "already installed")
        self._bindings[binding.skill_id] = binding

    def binding(self, skill_id: str) -> SkillBinding:
        """读取已安装且未撤销的绑定。"""
        try:
            binding = self._bindings[skill_id]
        except KeyError as error:
            raise SkillLifecycleError(skill_id, "lookup", "not installed") from error
        if skill_id in self._revoked:
            raise SkillLifecycleError(skill_id, "lookup", "revoked")
        return binding

    def is_installed(self, skill_id: str) -> bool:
        """判断 Skill 是否已有安装历史。"""
        return skill_id in self._bindings

    def revoke(self, skill_id: str) -> None:
        """把已安装 Skill 标记为撤销。"""
        if skill_id not in self._bindings:
            raise SkillLifecycleError(skill_id, "revoke", "not installed")
        if skill_id in self._revoked:
            raise SkillLifecycleError(skill_id, "revoke", "already revoked")
        self._revoked.add(skill_id)

    def snapshot(self) -> SkillStateSnapshot:
        """按 Skill ID 冻结安装与撤销状态。"""
        bindings = tuple(self._bindings[key] for key in sorted(self._bindings))
        return SkillStateSnapshot(bindings, tuple(sorted(self._revoked)))

    def restore(self, snapshot: SkillStateSnapshot) -> None:
        """恢复 checkpoint 中的安装与撤销状态。"""
        self._bindings = {binding.skill_id: binding for binding in snapshot.bindings}
        self._revoked = set(snapshot.revoked_skill_ids)


class InstrumentedSkill:
    """记录 install、load、invoke、return、revoke、unload。"""

    def __init__(self, recorder: RuntimeRecorder, state: SkillState) -> None:
        """绑定 Session Recorder 与 Run 级 SkillState。"""
        self._recorder = recorder
        self._state = state
        self._loaded: set[str] = set()
        self._active_invocations: set[str] = set()

    def install(self, binding: SkillBinding, actor: ActorCall) -> None:
        """安装固定 fixture 绑定并追加事件。"""
        self._state.register(binding)
        self._recorder.record_event(
            EventEmission(
                event_type=EventType.SKILL_INSTALL,
                actor=actor,
                metadata={
                    "skill_id": binding.skill_id,
                    "implementation": binding.implementation.root,
                },
            )
        )

    def load(self, skill_id: str, actor: ActorCall) -> None:
        """把已安装、未撤销 Skill 加载到当前 Session。"""
        self._state.binding(skill_id)
        if skill_id in self._loaded:
            raise SkillLifecycleError(skill_id, "load", "already loaded")
        self._recorder.record_event(
            EventEmission(
                event_type=EventType.SKILL_LOAD,
                actor=actor,
                metadata={"skill_id": skill_id},
            )
        )
        self._loaded.add(skill_id)

    def invoke(
        self,
        skill_id: str,
        input_artifact_ids: tuple[str, ...],
        actor: ActorCall,
    ) -> SkillInvocationToken:
        """记录显式调用并返回只能完成一次的 token。"""
        self._require_loaded(skill_id, "invoke")
        if actor.actor_id != skill_id:
            raise SkillLifecycleError(skill_id, "invoke", "actor mismatch")
        for artifact_id in input_artifact_ids:
            self._recorder.require_artifact(artifact_id)
        event = self._recorder.record_event(
            EventEmission(
                event_type=EventType.SKILL_INVOKE,
                actor=actor,
                input_artifact_ids=input_artifact_ids,
                metadata={"skill_id": skill_id},
            )
        )
        self._active_invocations.add(event.event_id)
        return SkillInvocationToken(skill_id, actor, input_artifact_ids, event.event_id)

    def return_output(
        self,
        invocation: SkillInvocationToken,
        content: bytes,
        parent_artifact_ids: tuple[str, ...],
        mime_type: str = "text/plain",
    ) -> Artifact:
        """完成调用，生成连接全部显式父节点的 Skill 输出。"""
        if invocation.invocation_event_id not in self._active_invocations:
            raise SkillLifecycleError(invocation.skill_id, "return", "invocation inactive")
        parents = tuple(self._recorder.require_artifact(item) for item in parent_artifact_ids)
        artifact = self._recorder.record_artifact(
            ArtifactEmission(
                event_type=EventType.SKILL_RETURN,
                artifact_type=ArtifactType.SKILL_OUTPUT,
                content=content,
                actor=invocation.actor,
                input_artifact_ids=parent_artifact_ids,
                origins=frozenset(
                    {invocation.skill_id}
                    | {origin for parent in parents for origin in parent.observed_label.origins}
                ),
                trust=TrustLevel.UNTRUSTED,
                mime_type=mime_type,
                metadata={"skill_id": invocation.skill_id},
            )
        )
        self._active_invocations.remove(invocation.invocation_event_id)
        return artifact

    def revoke(self, skill_id: str, actor: ActorCall) -> None:
        """由 Benchmark 特权入口追加撤销事件。"""
        self._state.revoke(skill_id)
        self._recorder.record_principal_revocation(skill_id, actor)

    def unload(self, skill_id: str, actor: ActorCall) -> None:
        """从当前 Session 卸载 Skill，不删除任何历史。"""
        self._require_loaded(skill_id, "unload", allow_revoked=True)
        self._recorder.record_event(
            EventEmission(
                event_type=EventType.SKILL_UNLOAD,
                actor=actor,
                metadata={"skill_id": skill_id},
            )
        )
        self._loaded.remove(skill_id)

    def binding(self, skill_id: str) -> SkillBinding:
        """返回当前可调用 Skill 的固定 fixture 绑定。"""
        self._require_loaded(skill_id, "invoke")
        return self._state.binding(skill_id)

    @property
    def loaded_skill_ids(self) -> tuple[str, ...]:
        """返回当前 Session 已加载 Skill 的稳定快照。"""
        return tuple(sorted(self._loaded))

    def snapshot(self) -> SkillRuntimeSnapshot:
        """冻结当前 Session 的加载与活动调用状态。"""
        return SkillRuntimeSnapshot(
            tuple(sorted(self._loaded)),
            tuple(sorted(self._active_invocations)),
        )

    def restore(self, snapshot: SkillRuntimeSnapshot) -> None:
        """恢复当前 Session 的加载状态。"""
        self._loaded = set(snapshot.loaded_skill_ids)
        self._active_invocations = set(snapshot.active_invocation_event_ids)

    def _require_loaded(
        self,
        skill_id: str,
        operation: str,
        *,
        allow_revoked: bool = False,
    ) -> None:
        if skill_id not in self._loaded:
            raise SkillLifecycleError(skill_id, operation, "not loaded")
        if not allow_revoked:
            self._state.binding(skill_id)
