"""Persistent Memory 插桩。"""

from dataclasses import dataclass

from skillflow.instrumentation.errors import MemoryKeyMissingError
from skillflow.models.enums import ArtifactType, EventType
from skillflow.models.provenance import Artifact
from skillflow.runtime.session import (
    ActorCall,
    ArtifactEmission,
    EventEmission,
    RuntimeRecorder,
)


@dataclass(frozen=True, slots=True)
class MemoryStateSnapshot:
    """Run 级 Memory 当前头的稳定快照。"""

    entries: tuple[tuple[str, str], ...]


class MemoryState:
    """一个 Run 内跨 Session 共享的当前 Memory 映射。"""

    def __init__(self) -> None:
        """MemoryState 的职责就是维护可变当前头。"""
        self._entries: dict[str, str] = {}

    def put(self, key: str, artifact_id: str) -> None:
        """设置当前版本。"""
        self._entries[key] = artifact_id

    def get(self, key: str) -> str:
        """读取当前版本 ID。"""
        try:
            return self._entries[key]
        except KeyError as error:
            raise MemoryKeyMissingError(key) from error

    def delete(self, key: str) -> None:
        """删除当前版本映射。"""
        try:
            del self._entries[key]
        except KeyError as error:
            raise MemoryKeyMissingError(key) from error

    def snapshot(self) -> MemoryStateSnapshot:
        """按 key 排序冻结当前 Memory 映射。"""
        return MemoryStateSnapshot(tuple(sorted(self._entries.items())))

    def restore(self, snapshot: MemoryStateSnapshot) -> None:
        """恢复 checkpoint 中的当前 Memory 映射。"""
        self._entries = dict(snapshot.entries)


class InstrumentedMemory:
    """记录 write、read、delete 的 Persistent Memory。"""

    def __init__(self, recorder: RuntimeRecorder, state: MemoryState) -> None:
        """绑定当前 Session Recorder 与 Run 级 MemoryState。"""
        self._recorder = recorder
        self._state = state

    def write(self, key: str, source_artifact_id: str, actor: ActorCall) -> Artifact:
        """把一个 Artifact 派生为新的 Memory 版本。"""
        source = self._recorder.require_artifact(source_artifact_id)
        artifact = self._recorder.record_artifact(
            ArtifactEmission(
                event_type=EventType.MEMORY_WRITE,
                artifact_type=ArtifactType.MEMORY,
                content=self._recorder.read_content(source_artifact_id),
                actor=actor,
                input_artifact_ids=(source_artifact_id,),
                origins=source.observed_label.origins,
                trust=source.observed_label.trust,
                mime_type=source.mime_type,
                metadata={"memory_key": key},
            )
        )
        self._state.put(key, artifact.artifact_id)
        self._recorder.set_memory_head(key, artifact)
        return artifact

    def read(self, key: str, actor: ActorCall) -> Artifact:
        """读取当前 Memory 版本并创建显式派生 Artifact。"""
        source_id = self._state.get(key)
        source = self._recorder.require_artifact(source_id)
        return self._recorder.record_artifact(
            ArtifactEmission(
                event_type=EventType.MEMORY_READ,
                artifact_type=ArtifactType.MEMORY,
                content=self._recorder.read_content(source_id),
                actor=actor,
                input_artifact_ids=(source_id,),
                origins=source.observed_label.origins,
                trust=source.observed_label.trust,
                mime_type=source.mime_type,
                metadata={"memory_key": key},
            )
        )

    def delete(self, key: str, actor: ActorCall) -> None:
        """追加删除 Event，再移除唯一可变的当前头。"""
        source_id = self._state.get(key)
        self._recorder.record_event(
            EventEmission(
                event_type=EventType.MEMORY_DELETE,
                actor=actor,
                input_artifact_ids=(source_id,),
                metadata={"memory_key": key},
            )
        )
        self._state.delete(key)
        self._recorder.delete_memory_head(key)
