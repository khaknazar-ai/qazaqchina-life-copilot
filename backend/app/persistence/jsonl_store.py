import json
import os
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from backend.app.persistence.errors import (
    PersistenceSerializationError,
    RecordNotFoundError,
)
from backend.app.persistence.models import (
    PersistenceWriteResult,
    StoredRecord,
    utc_now,
)

_STORE_LOCKS: dict[str, RLock] = {}
_STORE_LOCKS_GUARD = RLock()


class JsonlRecordStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        key = os.path.normcase(str(self.path.resolve()))
        with _STORE_LOCKS_GUARD:
            self._lock = _STORE_LOCKS.setdefault(key, RLock())

    def append(
        self,
        record_type: str,
        payload: dict[str, Any],
        record_id: str | None = None,
    ) -> PersistenceWriteResult:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        record = StoredRecord(
            record_id=record_id or str(uuid4()),
            record_type=record_type,
            payload=payload,
            created_at=utc_now(),
        )
        try:
            serialized = record.model_dump_json()
        except (TypeError, ValueError) as exc:
            raise PersistenceSerializationError(
                f"Could not serialize record '{record.record_id}'."
            ) from exc

        with self._lock, self.path.open("a+b") as record_file:
            record_file.seek(0, os.SEEK_END)
            size = record_file.tell()
            if size:
                record_file.seek(-1, os.SEEK_END)
                if record_file.read(1) != b"\n":
                    # Leave interrupted authoritative state untouched for recovery.
                    raise PersistenceSerializationError(
                        "JSONL store has an unterminated trailing record; append refused."
                    )
            record_file.write((serialized + "\n").encode("utf-8"))
            record_file.flush()
            os.fsync(record_file.fileno())

        return PersistenceWriteResult(
            record_id=record.record_id,
            path=str(self.path),
            written=True,
        )

    def list_records(self, record_type: str | None = None) -> list[StoredRecord]:
        with self._lock:
            return self._list_records(record_type)

    def _list_records(self, record_type: str | None = None) -> list[StoredRecord]:
        if not self.path.exists():
            return []

        records: list[StoredRecord] = []
        with self.path.open(encoding="utf-8") as record_file:
            for line in record_file:
                record = self._parse_line(line)
                if record is None:
                    continue
                if record_type is not None and record.record_type != record_type:
                    continue
                records.append(record)
        return records

    def get(self, record_id: str) -> StoredRecord:
        for record in reversed(self.list_records()):
            if record.record_id == record_id:
                return record
        raise RecordNotFoundError(f"Record '{record_id}' was not found.")

    def clear(self) -> None:
        with self._lock:
            if self.path.exists():
                self.path.unlink()

    @staticmethod
    def _parse_line(line: str) -> StoredRecord | None:
        raw_line = line.strip()
        if not raw_line:
            return None
        try:
            payload = json.loads(raw_line)
            return StoredRecord.model_validate(payload)
        except (json.JSONDecodeError, ValidationError, TypeError, ValueError):
            return None
