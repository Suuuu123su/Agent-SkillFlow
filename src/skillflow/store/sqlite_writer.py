"""SQLite EventStore 的原子写入事务。"""

import sqlite3

from skillflow.models.authorization import AuthorizationGrant
from skillflow.models.effects import EffectRecord
from skillflow.models.events import DecisionRecord, SecurityEvent
from skillflow.store.envelope_validation import validate_envelope
from skillflow.store.errors import StoreConflictError, StoreIntegrityError
from skillflow.store.event_store import (
    EventEnvelope,
    MemoryHead,
    RevocationRecord,
    RevocationTargetKind,
    StoredArtifact,
)


def append_envelope(connection: sqlite3.Connection, envelope: EventEnvelope) -> None:
    """在单个事务内追加 Event、边、Decision 和 Effect。"""
    event = envelope.event
    validate_envelope(envelope)
    try:
        with connection:
            connection.execute(
                "INSERT OR IGNORE INTO runs (run_id) VALUES (?)",
                (event.run_id,),
            )
            connection.execute(
                "INSERT OR IGNORE INTO sessions (run_id, session_id) VALUES (?, ?)",
                (event.run_id, event.session_id),
            )
            connection.execute(
                "INSERT OR IGNORE INTO principals (principal_id) VALUES (?)",
                (event.actor_id,),
            )
            connection.execute(
                """
                INSERT INTO events (
                    event_id, run_id, task_id, session_id, call_id, timestamp,
                    event_type, actor_id, decision_id, event_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.run_id,
                    event.task_id,
                    event.session_id,
                    event.call_id,
                    event.timestamp.isoformat(),
                    event.event_type.value,
                    event.actor_id,
                    event.decision_id,
                    event.model_dump_json(),
                ),
            )
            _insert_edges(connection, event)
            _insert_decision(connection, envelope.decision)
            _insert_effect(connection, envelope.effect)
            _insert_grant(connection, envelope.grant, event.event_id)
            _insert_revocation(connection, envelope.revocation)
    except sqlite3.IntegrityError as error:
        reason = str(error)
        if "events.event_id" in reason:
            raise StoreConflictError("event", event.event_id) from error
        raise StoreIntegrityError("append_event", reason) from error


def put_stored_artifact(
    connection: sqlite3.Connection,
    stored: StoredArtifact,
) -> None:
    """追加一个 Artifact 及其可选 Blob 引用。"""
    artifact = stored.artifact
    blob = stored.blob_ref
    if blob is not None and (
        blob.content_hash != artifact.content_hash or blob.content_length != artifact.content_length
    ):
        raise StoreIntegrityError("put_artifact", "Blob hash 或长度与 Artifact 不一致")
    try:
        with connection:
            connection.execute(
                """
                INSERT INTO artifacts (
                    artifact_id, created_by_event_id, artifact_json, blob_run_id, blob_ref_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    artifact.artifact_id,
                    artifact.created_by_event_id,
                    artifact.model_dump_json(),
                    None if blob is None else blob.run_id,
                    None if blob is None else blob.model_dump_json(),
                ),
            )
    except sqlite3.IntegrityError as error:
        raise StoreConflictError("artifact", artifact.artifact_id) from error


def update_memory_head(connection: sqlite3.Connection, head: MemoryHead) -> None:
    """只在生成 Event、输出边和 Run 一致时更新 Memory 头。"""
    matched = connection.execute(
        """
        SELECT 1
        FROM events
        JOIN event_outputs USING (event_id)
        WHERE events.event_id = ?
          AND events.run_id = ?
          AND events.session_id = ?
          AND event_outputs.artifact_id = ?
        """,
        (head.updated_event_id, head.run_id, head.session_id, head.artifact_id),
    ).fetchone()
    if matched is None:
        raise StoreIntegrityError("set_memory_head", "Memory 头与生成 Event 不一致")
    try:
        with connection:
            connection.execute(
                """
                INSERT INTO memory_heads (
                    run_id, memory_key, artifact_id, session_id, updated_event_id
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (run_id, memory_key) DO UPDATE SET
                    artifact_id = excluded.artifact_id,
                    session_id = excluded.session_id,
                    updated_event_id = excluded.updated_event_id
                """,
                (
                    head.run_id,
                    head.key,
                    head.artifact_id,
                    head.session_id,
                    head.updated_event_id,
                ),
            )
    except sqlite3.IntegrityError as error:
        raise StoreIntegrityError("set_memory_head", str(error)) from error


def _insert_edges(connection: sqlite3.Connection, event: SecurityEvent) -> None:
    connection.executemany(
        "INSERT INTO event_inputs (event_id, position, artifact_id) VALUES (?, ?, ?)",
        (
            (event.event_id, position, artifact_id)
            for position, artifact_id in enumerate(event.input_artifact_ids)
        ),
    )
    connection.executemany(
        "INSERT INTO event_outputs (event_id, position, artifact_id) VALUES (?, ?, ?)",
        (
            (event.event_id, position, artifact_id)
            for position, artifact_id in enumerate(event.output_artifact_ids)
        ),
    )


def _insert_decision(
    connection: sqlite3.Connection,
    decision: DecisionRecord | None,
) -> None:
    if decision is not None:
        connection.execute(
            "INSERT INTO decisions (decision_id, request_event_id, decision_json) VALUES (?, ?, ?)",
            (decision.decision_id, decision.request_event_id, decision.model_dump_json()),
        )


def _insert_effect(connection: sqlite3.Connection, effect: EffectRecord | None) -> None:
    if effect is not None:
        connection.execute(
            """
            INSERT INTO effects (
                effect_id, request_event_id, decision_id, result_event_id, effect_json
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                effect.effect_id,
                effect.request_event_id,
                effect.decision_id,
                effect.result_event_id,
                effect.model_dump_json(),
            ),
        )


def _insert_grant(
    connection: sqlite3.Connection,
    grant: AuthorizationGrant | None,
    issue_event_id: str,
) -> None:
    if grant is not None:
        connection.execute(
            "INSERT INTO grants (grant_id, issue_event_id, grant_json) VALUES (?, ?, ?)",
            (grant.grant_id, issue_event_id, grant.model_dump_json()),
        )


def _insert_revocation(
    connection: sqlite3.Connection,
    revocation: RevocationRecord | None,
) -> None:
    if revocation is not None:
        if revocation.target_kind is RevocationTargetKind.GRANT:
            exists = connection.execute(
                "SELECT 1 FROM grants WHERE grant_id = ?",
                (revocation.target_id,),
            ).fetchone()
            if exists is None:
                raise StoreIntegrityError(
                    "append_event",
                    f"AUTH_REVOKE 目标 Grant 不存在：{revocation.target_id}",
                )
        connection.execute(
            """
            INSERT INTO revocations (
                revocation_id, target_kind, target_id, event_id, timestamp
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                revocation.revocation_id,
                revocation.target_kind.value,
                revocation.target_id,
                revocation.event_id,
                revocation.timestamp.isoformat(),
            ),
        )
