from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


class StoredRecord(BaseModel):
    record_id: str
    record_type: str
    payload: dict[str, Any]
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime | None = None


class AdminDecisionRecord(BaseModel):
    decision_id: str
    review_type: str
    action: str
    admin_id: str
    target_id: str
    reason: str | None = None
    notes: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class VerificationRecord(BaseModel):
    record_id: str
    contributor_id: str
    requested_role: str
    decision: str | None = None
    admin_id: str | None = None
    reason: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class PersistenceWriteResult(BaseModel):
    record_id: str
    path: str | None = None
    written: bool = True
