"""当前 Session 的确定性运行依赖与事实记录。"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime

from pydantic import JsonValue

from skillflow.instrumentation.errors import ArtifactContentError
from skillflow.models.effects import CapabilityEffect, EffectRecord
from skillflow.models.enums import ArtifactType, EventType, ProvenanceMode, TrustLevel
from skillflow.models.events import DecisionRecord, SecurityEvent
from skillflow.models.provenance import Artifact, SecurityLabel
from skillflow.runtime.determinism import Clock, IdFactory
from skillflow.runtime.provenance import observed_origins
from skillflow.store.blob_store import RunBlobStore
from skillflow.store.event_store import EventEnvelope, EventStore, MemoryHead, StoredArtifact


@dataclass(frozen=True, slots=True)
class ActorCall:
    """事件实际主体和可选调用边界。"""

    actor_id: str
    call_id: str | None


@dataclass(frozen=True, slots=True)
class SessionIdentity:
    """当前 Run、Task 与 Session 标识。"""

    run_id: str
    task_id: str
    session_id: str


@dataclass(frozen=True, slots=True)
class RuntimeDependencies:
    """事实记录所需的存储与确定性依赖。"""

    event_store: EventStore
    blob_store: RunBlobStore
    clock: Clock
    id_factory: IdFactory
    provenance_mode: ProvenanceMode = ProvenanceMode.PRESERVE


@dataclass(frozen=True, slots=True)
class ArtifactFactIds:
    """允许相关记录在提交前引用同一 Event 和 Artifact。"""

    event_id: str
    artifact_id: str


@dataclass(frozen=True, slots=True)
class ArtifactEmission:
    """一次 Artifact 与生成 Event 的类型化输入。"""

    event_type: EventType
    artifact_type: ArtifactType
    content: bytes
    actor: ActorCall
    input_artifact_ids: tuple[str, ...] = ()
    origins: frozenset[str] = frozenset()
    trust: TrustLevel = TrustLevel.UNKNOWN
    mime_type: str = "application/octet-stream"
    requested_effect: CapabilityEffect | None = None
    decision_id: str | None = None
    decision: DecisionRecord | None = None
    effect: EffectRecord | None = None
    metadata: Mapping[str, JsonValue] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EventEmission:
    """一次无输出 Event 的类型化输入。"""

    event_type: EventType
    actor: ActorCall
    input_artifact_ids: tuple[str, ...] = ()
    requested_effect: CapabilityEffect | None = None
    decision_id: str | None = None
    decision: DecisionRecord | None = None
    effect: EffectRecord | None = None
    metadata: Mapping[str, JsonValue] = field(default_factory=dict)


class RuntimeRecorder:
    """把运行期事实追加到 EventStore 与 BlobStore。"""

    def __init__(self, identity: SessionIdentity, dependencies: RuntimeDependencies) -> None:
        """绑定当前 Session 身份和确定性持久化依赖。"""
        self._identity = identity
        self._dependencies = dependencies

    @property
    def identity(self) -> SessionIdentity:
        """返回当前 Session 的稳定身份。"""
        return self._identity

    def new_id(self, namespace: str) -> str:
        """从注入工厂分配确定性 ID。"""
        return self._dependencies.id_factory.new_id(namespace)

    def now(self) -> datetime:
        """读取注入的虚拟时间。"""
        return self._dependencies.clock.now()

    def allocate_artifact_ids(self) -> ArtifactFactIds:
        """在原子事实构造前预留确定性 Event 与 Artifact ID。"""
        return ArtifactFactIds(
            event_id=self.new_id("event"),
            artifact_id=self.new_id("artifact"),
        )

    def record_artifact(self, emission: ArtifactEmission) -> Artifact:
        """把 Blob、Artifact 元数据和生成 Event 追加到持久层。"""
        return self.record_prepared_artifact(self.allocate_artifact_ids(), emission)

    def record_prepared_artifact(
        self,
        fact_ids: ArtifactFactIds,
        emission: ArtifactEmission,
    ) -> Artifact:
        """用预留 ID 原子记录带 Decision/Effect 的 Artifact 事实。"""
        blob = self._dependencies.blob_store.put(emission.content)
        artifact = Artifact(
            artifact_id=fact_ids.artifact_id,
            artifact_type=emission.artifact_type,
            content_hash=blob.content_hash,
            content_length=blob.content_length,
            mime_type=emission.mime_type,
            created_by_event_id=fact_ids.event_id,
            observed_label=SecurityLabel(
                origins=observed_origins(
                    self._dependencies.provenance_mode,
                    emission.event_type,
                    emission.origins,
                ),
                trust=emission.trust,
                task_id=self._identity.task_id,
                created_session_id=self._identity.session_id,
                parent_artifact_ids=frozenset(emission.input_artifact_ids),
            ),
        )
        event = self._event(
            fact_ids.event_id,
            EventEmission(
                event_type=emission.event_type,
                actor=emission.actor,
                input_artifact_ids=emission.input_artifact_ids,
                requested_effect=emission.requested_effect,
                decision_id=emission.decision_id,
                decision=emission.decision,
                effect=emission.effect,
                metadata=emission.metadata,
            ),
            (fact_ids.artifact_id,),
        )
        self._dependencies.event_store.put_artifact(StoredArtifact(artifact, blob))
        self._dependencies.event_store.append_event(
            EventEnvelope(event, decision=emission.decision, effect=emission.effect)
        )
        return artifact

    def record_event(self, emission: EventEmission) -> SecurityEvent:
        """追加一个不产生 Artifact 的 Event。"""
        event = self._event(self.new_id("event"), emission, ())
        self._dependencies.event_store.append_event(
            EventEnvelope(event, decision=emission.decision, effect=emission.effect)
        )
        return event

    def require_artifact(self, artifact_id: str) -> Artifact:
        """读取存在的 Artifact，否则返回类型化错误。"""
        artifact = self._dependencies.event_store.get_artifact(artifact_id)
        if artifact is None:
            raise ArtifactContentError(artifact_id, "元数据不存在")
        return artifact

    def read_content(self, artifact_id: str) -> bytes:
        """经受控 Blob 引用读取 Artifact 内容。"""
        self.require_artifact(artifact_id)
        reference = self._dependencies.event_store.get_blob_ref(artifact_id)
        if reference is None:
            raise ArtifactContentError(artifact_id, "Blob 引用不存在")
        return self._dependencies.blob_store.get(reference)

    def set_memory_head(self, key: str, artifact: Artifact) -> None:
        """更新当前 Run 的 Memory 头。"""
        self._dependencies.event_store.set_memory_head(
            MemoryHead(
                run_id=self._identity.run_id,
                key=key,
                artifact_id=artifact.artifact_id,
                session_id=self._identity.session_id,
                updated_event_id=artifact.created_by_event_id,
            )
        )

    def delete_memory_head(self, key: str) -> None:
        """删除 Memory 当前头但保留历史。"""
        self._dependencies.event_store.delete_memory_head(self._identity.run_id, key)

    def _event(
        self,
        event_id: str,
        emission: EventEmission,
        output_artifact_ids: tuple[str, ...],
    ) -> SecurityEvent:
        return SecurityEvent(
            event_id=event_id,
            run_id=self._identity.run_id,
            task_id=self._identity.task_id,
            session_id=self._identity.session_id,
            call_id=emission.actor.call_id,
            timestamp=self._dependencies.clock.now(),
            event_type=emission.event_type,
            actor_id=emission.actor.actor_id,
            input_artifact_ids=emission.input_artifact_ids,
            output_artifact_ids=output_artifact_ids,
            requested_effect=emission.requested_effect,
            decision_id=emission.decision_id,
            metadata=dict(emission.metadata),
        )
