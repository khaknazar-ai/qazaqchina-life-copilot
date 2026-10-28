"""Atomic local attempt limits shared by chat and OCR, including failed calls."""

import sqlite3
import time
from contextlib import closing
from pathlib import Path


class CloudLimitError(Exception):
    pass


class CloudRequestBudget:
    def __init__(self, path: Path, daily_limit: int, per_minute: int) -> None:
        self.path = path
        self.daily_limit = daily_limit
        self.per_minute = per_minute

    def reserve(self, kind: str, *, now: float | None = None) -> None:
        timestamp = time.time() if now is None else now
        utc_day_start = timestamp - timestamp % 86400
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=5)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS cloud_attempts (created REAL, kind TEXT)")
            db.execute("BEGIN IMMEDIATE")
            daily, minute = db.execute(
                "SELECT COALESCE(SUM(created >= ?), 0), COALESCE(SUM(created > ?), 0) "
                "FROM cloud_attempts WHERE created >= ?",
                (utc_day_start, timestamp - 60, min(utc_day_start, timestamp - 60)),
            ).fetchone()
            if daily >= self.daily_limit or minute >= self.per_minute:
                raise CloudLimitError("cloud_request_limit")
            db.execute("INSERT INTO cloud_attempts VALUES (?, ?)", (timestamp, kind))
            db.execute("DELETE FROM cloud_attempts WHERE created < ?", (utc_day_start - 86400,))
