"""RuntimeRecorder 的类型化输入与依赖合同。"""

from collections.abc import Mapping
from dataclasses import dataclass, field

from pydantic import JsonValue

from skillflow.models.effects import CapabilityEffect, EffectRecord
from skillflow.models.enums import ArtifactType, EventType, ProvenanceMode, TrustLevel
from skillflow.models.events import DecisionRecord
from skillflow.runtime.determinism import Clock, IdFactory
from skillflow.store.blob_store import RunBlobStore
from skillflow.store.event_store import EventStore


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
