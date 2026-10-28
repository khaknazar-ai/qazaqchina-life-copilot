import hashlib
import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import RLock

from backend.app.domain.sources import SourceReference
from backend.app.source_conflicts.errors import ConflictIntegrityError
from backend.app.source_conflicts.models import ConflictCase, ConflictEvent, IntegrityReport


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def source_snapshot_payload(source: SourceReference) -> dict:
    payload = source.model_dump(mode="json")
    if not source.reviewed_answer_passages:
        payload.pop("reviewed_answer_passages", None)
    return payload


class ConflictStore:
    """A local event ledger. Database owners still need independent protected backups."""

    def __init__(self, db_path: Path | str = ":memory:") -> None:
        path = str(db_path)
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, timeout=10, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA recursive_triggers = ON")
        self._lock = RLock()
        with self.connection:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS conflict_source_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    snapshot_hash TEXT NOT NULL,
                    source_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS conflict_review_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    conflict_id TEXT,
                    revision INTEGER,
                    event_json TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    event_hash TEXT NOT NULL,
                    UNIQUE(conflict_id, revision)
                );
                CREATE INDEX IF NOT EXISTS conflict_review_case
                    ON conflict_review_events(conflict_id, revision DESC);
                CREATE TRIGGER IF NOT EXISTS conflict_snapshots_no_update
                    BEFORE UPDATE ON conflict_source_snapshots
                    BEGIN SELECT RAISE(ABORT, 'Conflict snapshots are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS conflict_snapshots_no_delete
                    BEFORE DELETE ON conflict_source_snapshots
                    BEGIN SELECT RAISE(ABORT, 'Conflict snapshots are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS conflict_snapshots_no_replace
                    BEFORE INSERT ON conflict_source_snapshots
                    WHEN EXISTS(SELECT 1 FROM conflict_source_snapshots
                        WHERE snapshot_id = NEW.snapshot_id)
                    BEGIN SELECT RAISE(ABORT, 'Conflict snapshots cannot be replaced'); END;
                CREATE TRIGGER IF NOT EXISTS conflict_events_no_update
                    BEFORE UPDATE ON conflict_review_events
                    BEGIN SELECT RAISE(ABORT, 'Conflict events are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS conflict_events_no_delete
                    BEFORE DELETE ON conflict_review_events
                    BEGIN SELECT RAISE(ABORT, 'Conflict events are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS conflict_events_no_replace
                    BEFORE INSERT ON conflict_review_events
                    WHEN EXISTS(SELECT 1 FROM conflict_review_events
                        WHERE sequence = NEW.sequence OR event_id = NEW.event_id
                        OR (conflict_id = NEW.conflict_id AND revision = NEW.revision))
                    BEGIN SELECT RAISE(ABORT, 'Conflict events cannot be replaced'); END;
                """
            )

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self._lock:
            self.connection.execute("BEGIN IMMEDIATE")
            try:
                self.assert_integrity()
                yield
                self.connection.commit()
            except Exception:
                self.connection.rollback()
                raise

    def save_snapshots(self, case: ConflictCase) -> None:
        for snapshot in case.sources:
            source_json = canonical_json(source_snapshot_payload(snapshot.source))
            existing = self.connection.execute(
                "SELECT source_json, snapshot_hash FROM conflict_source_snapshots "
                "WHERE snapshot_id = ?",
                (snapshot.snapshot_id,),
            ).fetchone()
            if existing:
                if existing["source_json"] != source_json or (
                    existing["snapshot_hash"] != snapshot.snapshot_hash
                ):
                    raise ConflictIntegrityError("Snapshot identity collision")
                continue
            self.connection.execute(
                "INSERT INTO conflict_source_snapshots VALUES (?, ?, ?)",
                (snapshot.snapshot_id, snapshot.snapshot_hash, source_json),
            )

    def snapshot_source_payload(self, snapshot_id: str) -> dict:
        row = self.connection.execute(
            "SELECT source_json FROM conflict_source_snapshots WHERE snapshot_id = ?",
            (snapshot_id,),
        ).fetchone()
        if row is None:
            raise ConflictIntegrityError("Preserved source snapshot is missing")
        return json.loads(row["source_json"])

    def append(self, event: dict) -> ConflictEvent:
        row = self.connection.execute(
            "SELECT sequence, event_hash FROM conflict_review_events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        sequence = row["sequence"] + 1 if row else 1
        previous_hash = row["event_hash"] if row else "0" * 64
        value = {**event, "sequence": sequence, "previous_hash": previous_hash}
        event_hash = digest(value)
        value["event_hash"] = event_hash
        self.connection.execute(
            "INSERT INTO conflict_review_events "
            "(sequence, event_id, conflict_id, revision, event_json, previous_hash, event_hash) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                sequence,
                value["event_id"],
                value.get("conflict_id"),
                value.get("revision"),
                canonical_json(value),
                previous_hash,
                event_hash,
            ),
        )
        return ConflictEvent.model_validate(value)

    def latest(self, conflict_id: str) -> ConflictCase | None:
        row = self.connection.execute(
            "SELECT event_json FROM conflict_review_events "
            "WHERE conflict_id = ? AND revision IS NOT NULL ORDER BY revision DESC LIMIT 1",
            (conflict_id,),
        ).fetchone()
        return ConflictCase.model_validate(json.loads(row[0])["payload"]) if row else None

    def cases(self) -> list[ConflictCase]:
        ids = self.connection.execute(
            "SELECT DISTINCT conflict_id FROM conflict_review_events "
            "WHERE revision IS NOT NULL ORDER BY conflict_id"
        ).fetchall()
        return [case for row in ids if (case := self.latest(row[0])) is not None]

    def history(self, conflict_id: str) -> list[ConflictEvent]:
        rows = self.connection.execute(
            "SELECT event_json FROM conflict_review_events "
            "WHERE conflict_id = ? OR revision IS NULL ORDER BY sequence",
            (conflict_id,),
        ).fetchall()
        events = [ConflictEvent.model_validate_json(row[0]) for row in rows]
        return [
            event
            for event in events
            if event.conflict_id == conflict_id
            or any(
                entry.get("conflict_id") == conflict_id
                for entry in event.payload.get("resolutions", [])
            )
        ]

    def assert_integrity(self) -> None:
        report = self.verify_integrity()
        if not report.passed:
            raise ConflictIntegrityError("Conflict ledger integrity check failed")

    def verify_integrity(self) -> IntegrityReport:
        with self._lock:
            rows = self.connection.execute(
                "SELECT * FROM conflict_review_events ORDER BY sequence"
            ).fetchall()
            snapshots = self.connection.execute(
                "SELECT * FROM conflict_source_snapshots"
            ).fetchall()
            snapshot_values: dict[str, tuple[str, dict]] = {}
            problems: list[str] = []
            for snapshot in snapshots:
                try:
                    source = json.loads(snapshot["source_json"])
                    if digest(source) != snapshot["snapshot_hash"]:
                        problems.append("snapshot_hash_mismatch")
                    snapshot_values[snapshot["snapshot_id"]] = (snapshot["snapshot_hash"], source)
                except (TypeError, ValueError):
                    problems.append("invalid_snapshot")
            previous_hash = "0" * 64
            revisions: dict[str, int] = {}
            for index, row in enumerate(rows, start=1):
                try:
                    value = json.loads(row["event_json"])
                    stored_hash = value.pop("event_hash")
                    if (
                        digest(value) != stored_hash
                        or row["event_hash"] != stored_hash
                        or row["previous_hash"] != previous_hash
                        or value["previous_hash"] != previous_hash
                        or row["sequence"] != index
                        or value["sequence"] != index
                        or value["event_id"] != row["event_id"]
                        or value.get("conflict_id") != row["conflict_id"]
                        or value.get("revision") != row["revision"]
                    ):
                        problems.append("event_chain_mismatch")
                    value["event_hash"] = stored_hash
                    event = ConflictEvent.model_validate(value)
                    if event.revision is not None:
                        case = ConflictCase.model_validate(event.payload)
                        expected = revisions.get(case.conflict_id, 0) + 1
                        if (
                            event.revision != expected
                            or case.revision != expected
                            or event.conflict_id != case.conflict_id
                        ):
                            problems.append("case_revision_mismatch")
                        revisions[case.conflict_id] = case.revision
                        for snapshot, preserved in zip(
                            case.sources, event.payload["sources"], strict=True
                        ):
                            expected_snapshot = snapshot_values.get(snapshot.snapshot_id)
                            if expected_snapshot != (
                                snapshot.snapshot_hash,
                                preserved["source"],
                            ):
                                problems.append("case_snapshot_mismatch")
                    previous_hash = stored_hash
                except (KeyError, TypeError, ValueError):
                    problems.append("invalid_event")
            return IntegrityReport(
                passed=not problems,
                event_count=len(rows),
                snapshot_count=len(snapshots),
                problems=list(dict.fromkeys(problems)),
            )

    def close(self) -> None:
        with self._lock:
            self.connection.close()

    def backup(self, destination: Path | str) -> IntegrityReport:
        """Create and verify a consistent SQLite copy without replacing an existing file."""
        path = Path(destination).resolve()
        project_root = Path(__file__).resolve().parents[3]
        if not path.is_relative_to(project_root) or path.exists():
            raise ValueError("Backup must use a new project-local file")
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self.assert_integrity()
            handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(handle)
            with sqlite3.connect(path) as copy:
                self.connection.backup(copy)
        restored = ConflictStore(path)
        try:
            report = restored.verify_integrity()
            restored.assert_integrity()
            return report
        finally:
            restored.close()
