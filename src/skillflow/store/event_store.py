"""EventStore Protocol 与内部写入值对象。"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum, unique
from typing import Protocol

from skillflow.models.authorization import AuthorizationGrant
from skillflow.models.effects import EffectRecord
from skillflow.models.events import DecisionRecord, SecurityEvent
from skillflow.models.provenance import Artifact
from skillflow.store.blob_store import BlobRef


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    """需要在一个事务内追加的事件及相关记录。"""

    event: SecurityEvent
    decision: DecisionRecord | None = None
    effect: EffectRecord | None = None
    grant: AuthorizationGrant | None = None
    revocation: "RevocationRecord | None" = None


@unique
class RevocationTargetKind(StrEnum):
    """追加式撤销事实允许指向的对象类型。"""

    GRANT = "grant"
    PRINCIPAL = "principal"


@dataclass(frozen=True, slots=True)
class RevocationRecord:
    """AUTH_REVOKE 或 SKILL_REVOKE 的不可变存储投影。"""

    revocation_id: str
    target_kind: RevocationTargetKind
    target_id: str
    event_id: str
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class StoredArtifact:
    """Artifact 元数据及其可选运行态 Blob 引用。"""

    artifact: Artifact
    blob_ref: BlobRef | None = None


@dataclass(frozen=True, slots=True)
class MemoryHead:
    """显式允许更新的 Persistent Memory 当前头。"""

    run_id: str
    key: str
    artifact_id: str
    session_id: str
    updated_event_id: str


class EventStore(Protocol):
    """追加式事件存储的最小可替换合同。"""

    def append_event(self, envelope: EventEnvelope) -> None:
        """原子追加事件、边、Decision 和 Effect。"""
        ...

    def get_event(self, event_id: str) -> SecurityEvent | None:
        """按 ID 读取事件。"""
        ...

    def iter_run_events(self, run_id: str) -> tuple[SecurityEvent, ...]:
        """按追加顺序读取一个 Run 的事件。"""
        ...

    def put_artifact(self, stored: StoredArtifact) -> None:
        """注册不可变 Artifact 元数据。"""
        ...

    def get_artifact(self, artifact_id: str) -> Artifact | None:
        """按 ID 读取 Artifact。"""
        ...

    def get_blob_ref(self, artifact_id: str) -> BlobRef | None:
        """读取 Artifact 对应的受控 Blob 引用。"""
        ...

    def get_decision(self, decision_id: str) -> DecisionRecord | None:
        """按 ID 读取决策记录。"""
        ...

    def get_effect(self, effect_id: str) -> EffectRecord | None:
        """按 ID 读取效果记录。"""
        ...

    def get_grant(self, grant_id: str) -> AuthorizationGrant | None:
        """按 ID 读取不可变 Grant。"""
        ...

    def iter_run_grants(self, run_id: str) -> tuple[AuthorizationGrant, ...]:
        """按签发 Event 顺序读取一个 Run 的 Grant。"""
        ...

    def iter_run_revocations(self, run_id: str) -> tuple[RevocationRecord, ...]:
        """按撤销 Event 顺序读取一个 Run 的撤销事实。"""
        ...

    def iter_run_effects(self, run_id: str) -> tuple[EffectRecord, ...]:
        """按请求事件顺序读取一个 Run 的 EffectRecord。"""
        ...

    def set_memory_head(self, head: MemoryHead) -> None:
        """更新唯一允许可变的 Persistent Memory 头。"""
        ...

    def get_memory_head(self, run_id: str, key: str) -> MemoryHead | None:
        """读取 Persistent Memory 当前头。"""
        ...

    def delete_memory_head(self, run_id: str, key: str) -> None:
        """删除可变 Memory 当前头，不触碰历史 Event。"""
        ...

    def flush(self) -> None:
        """把已完成事务刷新到持久介质。"""
        ...

    def close(self) -> None:
        """关闭存储资源。"""
        ...
