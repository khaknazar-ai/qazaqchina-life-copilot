"""Append-only review ledger with a read-only preflight mode."""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from urllib.parse import quote

from backend.app.source_corpus.store import canonical, digest


class EvaluationReviewStore:
    def __init__(self, path: Path | str, *, read_only: bool = False) -> None:
        self.read_only = read_only
        self._lock = RLock()
        self.connection: sqlite3.Connection | None = None
        if read_only and not Path(path).is_file():
            return
        if read_only:
            uri = "file:" + quote(Path(path).resolve().as_posix(), safe="/:") + "?mode=ro"
            self.connection = sqlite3.connect(uri, uri=True, timeout=10, check_same_thread=False)
        else:
            if str(path) != ":memory:":
                Path(path).parent.mkdir(parents=True, exist_ok=True)
            self.connection = sqlite3.connect(str(path), timeout=10, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        if not read_only:
            with self.connection:
                self.connection.execute("PRAGMA recursive_triggers=ON")
                self.connection.executescript("""
                    CREATE TABLE IF NOT EXISTS evaluation_reviews (
                        sequence INTEGER PRIMARY KEY,
                        case_id TEXT NOT NULL,
                        payload TEXT NOT NULL,
                        previous_hash TEXT NOT NULL,
                        event_hash TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS evaluation_review_case
                      ON evaluation_reviews(case_id);
                    CREATE TRIGGER IF NOT EXISTS evaluation_no_update BEFORE UPDATE
                      ON evaluation_reviews
                      BEGIN SELECT RAISE(ABORT, 'Reviews are append-only'); END;
                    CREATE TRIGGER IF NOT EXISTS evaluation_no_delete BEFORE DELETE
                      ON evaluation_reviews
                      BEGIN SELECT RAISE(ABORT, 'Reviews are append-only'); END;
                    CREATE TRIGGER IF NOT EXISTS evaluation_no_replace BEFORE INSERT
                      ON evaluation_reviews WHEN EXISTS(
                        SELECT 1 FROM evaluation_reviews WHERE sequence=NEW.sequence
                      ) BEGIN SELECT RAISE(ABORT, 'Reviews cannot be replaced'); END;
                """)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self._lock:
            if self.connection is None:
                yield
                return
            self.connection.execute("BEGIN" if self.read_only else "BEGIN IMMEDIATE")
            try:
                self.assert_integrity()
                yield
                self.connection.commit()
            except Exception:
                self.connection.rollback()
                raise

    def events(self) -> list[dict]:
        if self.connection is None:
            return []
        return [
            dict(row) | {"value": json.loads(row["payload"])}
            for row in self.connection.execute(
                "SELECT * FROM evaluation_reviews ORDER BY sequence",
            ).fetchall()
        ]

    def assert_integrity(self) -> None:
        previous = "0" * 64
        for number, event in enumerate(self.events(), 1):
            expected = digest(
                {
                    "sequence": number,
                    "case_id": event["case_id"],
                    "payload": event["value"],
                    "previous_hash": previous,
                }
            )
            if (
                event["sequence"] != number
                or event["previous_hash"] != previous
                or (event["event_hash"] != expected)
            ):
                raise ValueError("Evaluation review ledger integrity check failed")
            previous = event["event_hash"]

    def append(self, case_id: str, value: dict) -> None:
        if self.read_only or self.connection is None:
            raise PermissionError("Evaluation review storage is read-only")
        events = self.events()
        number = len(events) + 1
        previous = events[-1]["event_hash"] if events else "0" * 64
        event_hash = digest(
            {
                "sequence": number,
                "case_id": case_id,
                "payload": value,
                "previous_hash": previous,
            }
        )
        self.connection.execute(
            "INSERT INTO evaluation_reviews VALUES (?, ?, ?, ?, ?)",
            (number, case_id, canonical(value), previous, event_hash),
        )

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
