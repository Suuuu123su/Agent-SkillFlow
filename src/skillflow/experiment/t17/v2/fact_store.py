"""用于公开数据复算的只读内存存储，不创建新事件或文件。"""

from skillflow.experiment.t17.v2.portable_models import PortableRun
from skillflow.models.authorization import AuthorizationGrant
from skillflow.models.effects import EffectRecord
from skillflow.models.events import DecisionRecord, SecurityEvent
from skillflow.models.provenance import Artifact
from skillflow.store.blob_store import BlobRef
from skillflow.store.event_store import EventEnvelope, MemoryHead, RevocationRecord, StoredArtifact


class FactStore:
    """实现既有 EventStore 只读方法，所有写方法都拒绝。"""

    def __init__(self, facts: PortableRun) -> None:
        """不接受跨 Run、重复身份、游离 Artifact 或授权记录。"""
        self._facts = facts
        if not facts.events or any(e.run_id != facts.run_id for e in facts.events):
            raise ValueError("v2_portable_run_binding")
        self._events = {e.event_id: e for e in facts.events}
        self._artifacts = {a.artifact_id: a for a in facts.artifacts}
        self._decisions = {d.decision_id: d for d in facts.decisions}
        self._effects = {e.effect_id: e for e in facts.effects}
        self._grants = {g.grant_id: g for g in facts.grants}
        collections = (
            (self._events, facts.events),
            (self._artifacts, facts.artifacts),
            (self._decisions, facts.decisions),
            (self._effects, facts.effects),
            (self._grants, facts.grants),
        )
        if any(len(index) != len(values) for index, values in collections):
            raise ValueError("v2_portable_duplicate_identity")
        outputs = {a for e in facts.events for a in e.output_artifact_ids}
        if outputs != set(self._artifacts):
            raise ValueError("v2_portable_artifact_coverage")
        for artifact in facts.artifacts:
            event = self._events.get(artifact.created_by_event_id)
            if (
                event is None
                or artifact.artifact_id not in event.output_artifact_ids
                or event.session_id != artifact.observed_label.created_session_id
            ):
                raise ValueError("v2_portable_artifact_run_binding")
        for decision in facts.decisions:
            event = self._events.get(decision.request_event_id)
            if (
                event is None
                or decision.manifest_id != event.actor_id
                or not set(decision.matched_grant_ids) <= self._grants.keys()
            ):
                raise ValueError("v2_portable_decision_grant_binding")

    def get_event(self, event_id: str) -> SecurityEvent | None:
        """按当前 Run 的 ID 查找事件。"""
        return self._events.get(event_id)

    def iter_run_events(self, run_id: str) -> tuple[SecurityEvent, ...]:
        """保持实际追加顺序。"""
        return self._facts.events if run_id == self._facts.run_id else ()

    def get_artifact(self, artifact_id: str) -> Artifact | None:
        """返回元数据，不返回正文。"""
        return self._artifacts.get(artifact_id)

    def get_blob_ref(self, artifact_id: str) -> BlobRef | None:
        """可复算公开数据不携带文件系统引用。"""
        del artifact_id
        return None

    def get_decision(self, decision_id: str) -> DecisionRecord | None:
        """返回受信决策。"""
        return self._decisions.get(decision_id)

    def get_effect(self, effect_id: str) -> EffectRecord | None:
        """返回实际操作事实。"""
        return self._effects.get(effect_id)

    def get_grant(self, grant_id: str) -> AuthorizationGrant | None:
        """读取当前 Run 中签发的授权。"""
        return self._grants.get(grant_id)

    def iter_run_grants(self, run_id: str) -> tuple[AuthorizationGrant, ...]:
        """按原始顺序返回授权。"""
        return self._facts.grants if run_id == self._facts.run_id else ()

    def iter_run_effects(self, run_id: str) -> tuple[EffectRecord, ...]:
        """返回该 Run 的执行事实。"""
        return self._facts.effects if run_id == self._facts.run_id else ()

    def iter_run_revocations(self, run_id: str) -> tuple[RevocationRecord, ...]:
        """返回不可变撤销事件。"""
        return self._facts.revocations if run_id == self._facts.run_id else ()

    def get_memory_head(self, run_id: str, key: str) -> MemoryHead | None:
        """复算不重新执行工具，也不重建可变内存头。"""
        del run_id, key
        return None

    def append_event(self, envelope: EventEnvelope) -> None:
        """公开数据存储不能执行写入。"""
        del envelope
        raise TypeError("v2_fact_store_read_only")

    def put_artifact(self, stored: StoredArtifact) -> None:
        """拒绝生成输出。"""
        del stored
        raise TypeError("v2_fact_store_read_only")

    def set_memory_head(self, head: MemoryHead) -> None:
        """拒绝生成持久状态。"""
        del head
        raise TypeError("v2_fact_store_read_only")

    def delete_memory_head(self, run_id: str, key: str) -> None:
        """拒绝删除历史内容。"""
        del run_id, key
        raise TypeError("v2_fact_store_read_only")

    def flush(self) -> None:
        """内存只读视图没有待写数据。"""

    def close(self) -> None:
        """内存只读视图没有文件句柄。"""
