"""SQLite EventStore 实现。"""

import sqlite3
from pathlib import Path
from types import TracebackType
from typing import Self

from skillflow.models.effects import EffectRecord
from skillflow.models.events import DecisionRecord, SecurityEvent
from skillflow.models.provenance import Artifact
from skillflow.store.blob_store import BlobRef
from skillflow.store.errors import StoreClosedError
from skillflow.store.event_store import EventEnvelope, MemoryHead, StoredArtifact
from skillflow.store.sqlite_writer import (
    append_envelope,
    put_stored_artifact,
    update_memory_head,
)


class SqliteEventStore:
    """使用 SQLite 保存追加式安全事实的状态资源。"""

    def __init__(self, database: Path) -> None:
        """打开数据库并幂等初始化 T04 Schema。"""
        database.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(database)
        self._connection.execute("PRAGMA foreign_keys = ON")
        schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
        self._connection.executescript(schema)
        self._closed = False

    def __enter__(self) -> Self:
        """进入打开的数据库资源上下文。"""
        self._ensure_open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """退出上下文时关闭数据库。"""
        self.close()

    def append_event(self, envelope: EventEnvelope) -> None:
        """原子追加 Event、关系边、Decision 和 Effect。"""
        self._ensure_open()
        append_envelope(self._connection, envelope)

    def get_event(self, event_id: str) -> SecurityEvent | None:
        """按 ID 读取不可变 Event。"""
        row = self._fetch_one("SELECT event_json FROM events WHERE event_id = ?", event_id)
        return None if row is None else SecurityEvent.model_validate_json(row)

    def iter_run_events(self, run_id: str) -> tuple[SecurityEvent, ...]:
        """按自增序号返回一个 Run 的稳定事件序列。"""
        self._ensure_open()
        rows = self._connection.execute(
            "SELECT event_json FROM events WHERE run_id = ? ORDER BY sequence_number",
            (run_id,),
        ).fetchall()
        return tuple(SecurityEvent.model_validate_json(row[0]) for row in rows)

    def put_artifact(self, stored: StoredArtifact) -> None:
        """注册 Artifact 元数据和可选 Blob 引用。"""
        self._ensure_open()
        put_stored_artifact(self._connection, stored)

    def get_artifact(self, artifact_id: str) -> Artifact | None:
        """按 ID 读取 Artifact。"""
        row = self._fetch_one(
            "SELECT artifact_json FROM artifacts WHERE artifact_id = ?",
            artifact_id,
        )
        return None if row is None else Artifact.model_validate_json(row)

    def get_blob_ref(self, artifact_id: str) -> BlobRef | None:
        """读取 Artifact 对应的不透明 Blob 引用。"""
        row = self._fetch_one(
            "SELECT blob_ref_json FROM artifacts WHERE artifact_id = ?",
            artifact_id,
        )
        return None if row is None or row == "" else BlobRef.model_validate_json(row)

    def get_decision(self, decision_id: str) -> DecisionRecord | None:
        """按 ID 读取 DecisionRecord。"""
        row = self._fetch_one(
            "SELECT decision_json FROM decisions WHERE decision_id = ?",
            decision_id,
        )
        return None if row is None else DecisionRecord.model_validate_json(row)

    def get_effect(self, effect_id: str) -> EffectRecord | None:
        """按 ID 读取 EffectRecord。"""
        row = self._fetch_one(
            "SELECT effect_json FROM effects WHERE effect_id = ?",
            effect_id,
        )
        return None if row is None else EffectRecord.model_validate_json(row)

    def set_memory_head(self, head: MemoryHead) -> None:
        """更新明确允许可变的 Memory 头。"""
        self._ensure_open()
        update_memory_head(self._connection, head)

    def get_memory_head(self, run_id: str, key: str) -> MemoryHead | None:
        """读取 Persistent Memory 当前头。"""
        self._ensure_open()
        row = self._connection.execute(
            """
            SELECT run_id, memory_key, artifact_id, session_id, updated_event_id
            FROM memory_heads
            WHERE run_id = ? AND memory_key = ?
            """,
            (run_id, key),
        ).fetchone()
        if row is None:
            return None
        return MemoryHead(
            run_id=str(row[0]),
            key=str(row[1]),
            artifact_id=str(row[2]),
            session_id=str(row[3]),
            updated_event_id=str(row[4]),
        )

    def flush(self) -> None:
        """提交当前连接中已完成的事务。"""
        self._ensure_open()
        self._connection.commit()

    def close(self) -> None:
        """提交并关闭数据库连接。"""
        if not self._closed:
            self._connection.commit()
            self._connection.close()
            self._closed = True

    def _fetch_one(self, statement: str, identifier: str) -> str | None:
        self._ensure_open()
        row = self._connection.execute(statement, (identifier,)).fetchone()
        return None if row is None or row[0] is None else str(row[0])

    def _ensure_open(self) -> None:
        if self._closed:
            raise StoreClosedError(resource="EventStore")
