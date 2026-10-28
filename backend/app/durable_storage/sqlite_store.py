import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from backend.app.durable_storage.models import DurableStorageHealthReport

EXPECTED_TABLES = [
    "admin_audit_events",
    "citizen_feedback",
    "escalation_requests",
    "source_review_audit",
    "conversation_turns",
    "photo_intake_metadata",
    "privacy_delete_requests",
]

SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS admin_audit_events (
        event_id TEXT PRIMARY KEY,
        event_type TEXT NOT NULL,
        actor_id TEXT,
        target_type TEXT,
        target_id TEXT,
        reason TEXT,
        metadata_json TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS citizen_feedback (
        feedback_id TEXT PRIMARY KEY,
        user_id TEXT,
        session_id TEXT,
        category TEXT,
        message TEXT NOT NULL,
        severity TEXT,
        status TEXT,
        metadata_json TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS escalation_requests (
        escalation_id TEXT PRIMARY KEY,
        user_id TEXT,
        session_id TEXT,
        scenario TEXT,
        risk_level TEXT,
        summary TEXT NOT NULL,
        status TEXT,
        assigned_to TEXT,
        metadata_json TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS source_review_audit (
        review_event_id TEXT PRIMARY KEY,
        source_id TEXT,
        candidate_id TEXT,
        version_id TEXT,
        reviewer_id TEXT,
        decision TEXT NOT NULL,
        reason TEXT,
        metadata_json TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS conversation_turns (
        turn_id TEXT PRIMARY KEY,
        user_id TEXT,
        session_id TEXT,
        role TEXT NOT NULL,
        text TEXT NOT NULL,
        scenario TEXT,
        risk_level TEXT,
        metadata_json TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS photo_intake_metadata (
        photo_event_id TEXT PRIMARY KEY,
        user_id TEXT,
        session_id TEXT,
        image_hash TEXT,
        detected_type TEXT,
        size_bytes INTEGER,
        manual_transcription_used INTEGER,
        not_trusted_evidence INTEGER,
        metadata_json TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS privacy_delete_requests (
        request_id TEXT PRIMARY KEY,
        user_id TEXT,
        session_id TEXT,
        request_type TEXT NOT NULL,
        target_scope TEXT,
        status TEXT,
        message_redacted TEXT NOT NULL,
        contact_redacted TEXT,
        metadata_json TEXT,
        pii_detected INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
]


class SQLiteDurableStore:
    def __init__(self, db_path: Path | str, auto_initialize: bool = True) -> None:
        self.db_path = str(db_path)
        self._memory_connection: sqlite3.Connection | None = None
        if auto_initialize:
            self.initialize()

    def initialize(self) -> None:
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as connection:
            for statement in SCHEMA_STATEMENTS:
                connection.execute(statement)
            connection.commit()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        if self.db_path == ":memory:":
            if self._memory_connection is None:
                self._memory_connection = sqlite3.connect(":memory:")
                self._memory_connection.row_factory = sqlite3.Row
            yield self._memory_connection
            return

        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
        finally:
            connection.close()

    def execute(self, sql: str, parameters: tuple[Any, ...] = ()) -> None:
        with self.connection() as connection:
            connection.execute(sql, parameters)
            connection.commit()

    def query(self, sql: str, parameters: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = connection.execute(sql, parameters).fetchall()
            return [dict(row) for row in rows]

    def health_check(self) -> DurableStorageHealthReport:
        with self.connection() as connection:
            existing_tables = {
                row["name"]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            record_counts = {
                table: int(
                    connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()[0]
                )
                for table in EXPECTED_TABLES
                if table in existing_tables
            }
        expected_tables_present = all(table in existing_tables for table in EXPECTED_TABLES)
        warnings = [
            "SQLite durable storage is a local/dev foundation, not the final production database."
        ]
        recommendations = [
            "Future production storage should use PostgreSQL or a managed database.",
            "Add migrations, backups, encryption policy, retention rules, and RBAC before beta.",
        ]
        return DurableStorageHealthReport(
            db_path=self.db_path,
            initialized=expected_tables_present,
            table_count=len(existing_tables),
            expected_tables_present=expected_tables_present,
            record_counts=record_counts,
            raw_image_storage_allowed=False,
            production_database=False,
            used_network=False,
            warnings=warnings,
            recommendations=recommendations,
        )
