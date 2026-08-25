PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS schema_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
) WITHOUT ROWID;

INSERT OR IGNORE INTO schema_metadata (key, value) VALUES ('schema_version', '1');

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS sessions (
    run_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    PRIMARY KEY (run_id, session_id),
    FOREIGN KEY (run_id) REFERENCES runs (run_id)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS principals (
    principal_id TEXT PRIMARY KEY,
    principal_type TEXT
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id TEXT PRIMARY KEY,
    created_by_event_id TEXT NOT NULL,
    artifact_json TEXT NOT NULL,
    blob_run_id TEXT,
    blob_ref_json TEXT
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS events (
    sequence_number INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    run_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    call_id TEXT,
    timestamp TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    decision_id TEXT,
    event_json TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs (run_id),
    FOREIGN KEY (run_id, session_id) REFERENCES sessions (run_id, session_id),
    FOREIGN KEY (actor_id) REFERENCES principals (principal_id),
    FOREIGN KEY (decision_id) REFERENCES decisions (decision_id)
        DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS event_inputs (
    event_id TEXT NOT NULL,
    position INTEGER NOT NULL CHECK (position >= 0),
    artifact_id TEXT NOT NULL,
    PRIMARY KEY (event_id, position),
    UNIQUE (event_id, artifact_id),
    FOREIGN KEY (event_id) REFERENCES events (event_id),
    FOREIGN KEY (artifact_id) REFERENCES artifacts (artifact_id)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS event_outputs (
    event_id TEXT NOT NULL,
    position INTEGER NOT NULL CHECK (position >= 0),
    artifact_id TEXT NOT NULL UNIQUE,
    PRIMARY KEY (event_id, position),
    UNIQUE (event_id, artifact_id),
    FOREIGN KEY (event_id) REFERENCES events (event_id),
    FOREIGN KEY (artifact_id) REFERENCES artifacts (artifact_id)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS grants (
    grant_id TEXT PRIMARY KEY,
    issue_event_id TEXT NOT NULL,
    grant_json TEXT NOT NULL,
    FOREIGN KEY (issue_event_id) REFERENCES events (event_id)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS decisions (
    decision_id TEXT PRIMARY KEY,
    request_event_id TEXT NOT NULL UNIQUE,
    decision_json TEXT NOT NULL,
    FOREIGN KEY (request_event_id) REFERENCES events (event_id)
        DEFERRABLE INITIALLY DEFERRED
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS effects (
    effect_id TEXT PRIMARY KEY,
    request_event_id TEXT NOT NULL,
    decision_id TEXT NOT NULL,
    result_event_id TEXT,
    effect_json TEXT NOT NULL,
    FOREIGN KEY (request_event_id) REFERENCES events (event_id)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (decision_id) REFERENCES decisions (decision_id)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (result_event_id) REFERENCES events (event_id)
        DEFERRABLE INITIALLY DEFERRED
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS revocations (
    revocation_id TEXT PRIMARY KEY,
    target_kind TEXT NOT NULL,
    target_id TEXT NOT NULL,
    event_id TEXT NOT NULL UNIQUE,
    timestamp TEXT NOT NULL,
    FOREIGN KEY (event_id) REFERENCES events (event_id)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS memory_heads (
    run_id TEXT NOT NULL,
    memory_key TEXT NOT NULL,
    artifact_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    updated_event_id TEXT NOT NULL,
    PRIMARY KEY (run_id, memory_key),
    FOREIGN KEY (run_id) REFERENCES runs (run_id),
    FOREIGN KEY (artifact_id) REFERENCES artifacts (artifact_id),
    FOREIGN KEY (updated_event_id) REFERENCES events (event_id)
) WITHOUT ROWID;

CREATE TRIGGER IF NOT EXISTS event_output_creator_matches
BEFORE INSERT ON event_outputs
WHEN NOT EXISTS (
    SELECT 1
    FROM artifacts
    WHERE artifact_id = NEW.artifact_id
      AND created_by_event_id = NEW.event_id
)
BEGIN
    SELECT RAISE(ABORT, 'output artifact creator mismatch');
END;

CREATE TRIGGER IF NOT EXISTS event_output_blob_run_matches
BEFORE INSERT ON event_outputs
WHEN EXISTS (
    SELECT 1
    FROM artifacts
    JOIN events ON events.event_id = NEW.event_id
    WHERE artifacts.artifact_id = NEW.artifact_id
      AND artifacts.blob_run_id IS NOT NULL
      AND artifacts.blob_run_id != events.run_id
)
BEGIN
    SELECT RAISE(ABORT, 'output Blob belongs to another run');
END;

CREATE TRIGGER IF NOT EXISTS events_reject_update
BEFORE UPDATE ON events
BEGIN
    SELECT RAISE(ABORT, 'events are append-only');
END;

CREATE TRIGGER IF NOT EXISTS events_reject_delete
BEFORE DELETE ON events
BEGIN
    SELECT RAISE(ABORT, 'events are append-only');
END;

CREATE TRIGGER IF NOT EXISTS event_inputs_reject_update
BEFORE UPDATE ON event_inputs
BEGIN
    SELECT RAISE(ABORT, 'event_inputs are append-only');
END;

CREATE TRIGGER IF NOT EXISTS event_inputs_reject_delete
BEFORE DELETE ON event_inputs
BEGIN
    SELECT RAISE(ABORT, 'event_inputs are append-only');
END;

CREATE TRIGGER IF NOT EXISTS event_outputs_reject_update
BEFORE UPDATE ON event_outputs
BEGIN
    SELECT RAISE(ABORT, 'event_outputs are append-only');
END;

CREATE TRIGGER IF NOT EXISTS event_outputs_reject_delete
BEFORE DELETE ON event_outputs
BEGIN
    SELECT RAISE(ABORT, 'event_outputs are append-only');
END;

CREATE TRIGGER IF NOT EXISTS grants_reject_update
BEFORE UPDATE ON grants
BEGIN
    SELECT RAISE(ABORT, 'grants are append-only');
END;

CREATE TRIGGER IF NOT EXISTS grants_reject_delete
BEFORE DELETE ON grants
BEGIN
    SELECT RAISE(ABORT, 'grants are append-only');
END;

CREATE TRIGGER IF NOT EXISTS revocations_reject_update
BEFORE UPDATE ON revocations
BEGIN
    SELECT RAISE(ABORT, 'revocations are append-only');
END;

CREATE TRIGGER IF NOT EXISTS revocations_reject_delete
BEFORE DELETE ON revocations
BEGIN
    SELECT RAISE(ABORT, 'revocations are append-only');
END;
