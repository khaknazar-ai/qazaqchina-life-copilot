from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

SourceAcquisitionStatus = Literal[
    "new",
    "assigned",
    "researching",
    "candidate_created",
    "in_review",
    "approved_for_publishing_preview",
    "blocked",
    "closed",
]


def utc_now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class SourceAcquisitionTaskRecord(BaseModel):
    task_id: str = Field(default_factory=lambda: f"source-acq-{uuid4().hex}")
    domain: str
    priority: str
    target_trust_tier: str
    description: str
    suggested_owner_role: str
    assigned_to: str | None = None
    status: SourceAcquisitionStatus = "new"
    acceptance_criteria: list[str] = Field(default_factory=list)
    not_trusted_until_reviewed: bool = True
    source_candidate_id: str | None = None
    notes: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @field_validator("created_at", "updated_at")
    @classmethod
    def _timestamps_must_be_utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value)


class SourceAcquisitionCreateRequest(BaseModel):
    domain: str
    priority: str
    target_trust_tier: str
    description: str
    suggested_owner_role: str
    acceptance_criteria: list[str] = Field(default_factory=list)
    assigned_to: str | None = None
    notes: list[str] = Field(default_factory=list)


class SourceAcquisitionUpdateRequest(BaseModel):
    status: SourceAcquisitionStatus | None = None
    assigned_to: str | None = None
    source_candidate_id: str | None = None
    note: str | None = None


class SourceAcquisitionSummary(BaseModel):
    total_tasks: int
    open_tasks: int
    critical_tasks: int
    assigned_tasks: int
    candidate_created_count: int
    not_trusted_until_reviewed_count: int
    used_network: bool = False
    used_external_provider: bool = False
    warnings: list[str] = Field(default_factory=list)
