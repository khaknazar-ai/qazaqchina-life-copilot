from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

SourcePublishStatus = Literal[
    "draft",
    "validated",
    "ready_for_publish",
    "blocked",
    "published_preview",
    "applied",
    "rejected",
]


def utc_now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class SourcePublishRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: f"publish-request-{uuid4().hex}")
    source_id: str
    version_id: str | None = None
    candidate_id: str | None = None
    requested_by: str | None = None
    target_registry: str | None = None
    reason: str | None = None
    apply: bool = False
    confirm_registry_write: bool = False
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("created_at")
    @classmethod
    def _created_at_must_be_utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value)


class SourcePublishValidationIssue(BaseModel):
    issue_id: str
    severity: str
    message: str
    field: str | None = None


class SourcePublishPlan(BaseModel):
    request_id: str
    source_id: str
    version_id: str | None = None
    target_registry: str | None = None
    status: SourcePublishStatus
    registry_modified: bool = False
    planned_action: str
    changed_fields: list[str] = Field(default_factory=list)
    issues: list[SourcePublishValidationIssue] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    rollback_available: bool = False
    supersedes_version_id: str | None = None


class SourcePublishManifest(BaseModel):
    generated_at: datetime = Field(default_factory=utc_now)
    total_requests: int
    publishable_count: int
    blocked_count: int
    registry_modified: bool = False
    plans: list[SourcePublishPlan]
    used_network: bool = False
    used_external_provider: bool = False
    notes: list[str] = Field(default_factory=list)

    @field_validator("generated_at")
    @classmethod
    def _generated_at_must_be_utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value)
