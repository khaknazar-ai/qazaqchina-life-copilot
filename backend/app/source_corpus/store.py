"""Append-only local review events; protected backups remain necessary."""

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import RLock


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


class CorpusStore:
    def __init__(self, database_path: str | Path = ":memory:", *, readonly: bool = False) -> None:
        self.readonly = readonly
        if readonly:
            if str(database_path) == ":memory:":
                raise ValueError("Read-only inspection requires an existing ledger")
            uri = Path(database_path).resolve().as_uri() + "?mode=ro"
            self.connection = sqlite3.connect(uri, uri=True, timeout=10, check_same_thread=False)
        else:
            if str(database_path) != ":memory:":
                Path(database_path).parent.mkdir(parents=True, exist_ok=True)
            self.connection = sqlite3.connect(
                str(database_path), timeout=10, check_same_thread=False
            )
        self.connection.row_factory = sqlite3.Row
        self._lock = RLock()
        if readonly:
            self.connection.execute("PRAGMA query_only=ON")
            return
        with self.connection:
            self.connection.execute("PRAGMA recursive_triggers=ON")
            self.connection.executescript("""
                CREATE TABLE IF NOT EXISTS corpus_events (
                    sequence INTEGER PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    event_hash TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS corpus_events_source ON corpus_events(source_id);
                CREATE TRIGGER IF NOT EXISTS corpus_events_no_update BEFORE UPDATE ON corpus_events
                  BEGIN SELECT RAISE(ABORT, 'Corpus events are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS corpus_events_no_delete BEFORE DELETE ON corpus_events
                  BEGIN SELECT RAISE(ABORT, 'Corpus events are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS corpus_events_no_replace BEFORE INSERT ON corpus_events
                  WHEN EXISTS(SELECT 1 FROM corpus_events WHERE sequence=NEW.sequence)
                  BEGIN SELECT RAISE(ABORT, 'Corpus events cannot be replaced'); END;
            """)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self._lock:
            self.connection.execute("BEGIN" if self.readonly else "BEGIN IMMEDIATE")
            try:
                self.assert_integrity()
                yield
                self.connection.commit()
            except Exception:
                self.connection.rollback()
                raise

    def events(self) -> list[dict]:
        rows = self.connection.execute("SELECT * FROM corpus_events ORDER BY sequence").fetchall()
        return [dict(row) | {"value": json.loads(row["payload"])} for row in rows]

    def assert_integrity(self) -> None:
        previous_hash = "0" * 64
        for sequence, event in enumerate(self.events(), 1):
            value = {
                "sequence": sequence,
                "source_id": event["source_id"],
                "payload": event["value"],
                "previous_hash": previous_hash,
            }
            if (
                event["sequence"] != sequence
                or event["previous_hash"] != previous_hash
                or event["event_hash"] != digest(value)
            ):
                raise ValueError("Corpus ledger integrity check failed")
            previous_hash = event["event_hash"]

    def append(self, source_id: str, value: dict) -> None:
        if self.readonly:
            raise PermissionError("Read-only inspection cannot change the ledger")
        events = self.events()
        sequence = len(events) + 1
        previous_hash = events[-1]["event_hash"] if events else "0" * 64
        event_hash = digest(
            {
                "sequence": sequence,
                "source_id": source_id,
                "payload": value,
                "previous_hash": previous_hash,
            }
        )
        self.connection.execute(
            "INSERT INTO corpus_events VALUES (?, ?, ?, ?, ?)",
            (sequence, source_id, canonical(value), previous_hash, event_hash),
        )

    def close(self) -> None:
        self.connection.close()
