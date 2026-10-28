from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

SourceVersionStatus = Literal[
    "draft",
    "approved",
    "published",
    "deprecated",
    "superseded",
]


def utc_now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class SourceVersionRecord(BaseModel):
    source_id: str
    version_id: str
    title: str
    url: str | None = None
    source_type: str | None = None
    trust_level: str | None = None
    language: str | None = None
    country: str | None = None
    city: str | None = None
    content_preview: str | None = None
    content_hash: str | None = None
    freshness_status: str | None = None
    status: SourceVersionStatus = "draft"
    parent_version_id: str | None = None
    reviewer_id: str | None = None
    review_reason: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    reviewed_at: datetime | None = None
    published_at: datetime | None = None
    warnings: list[str] = Field(default_factory=list)

    @field_validator("created_at", "reviewed_at", "published_at")
    @classmethod
    def _datetime_must_be_utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value)


class SourceVersionDiff(BaseModel):
    source_id: str
    previous_version_id: str | None = None
    new_version_id: str
    changed_fields: list[str] = Field(default_factory=list)
    content_hash_changed: bool = False
    warnings: list[str] = Field(default_factory=list)


class SourcePublishPreview(BaseModel):
    total_versions: int
    draft_versions: int
    approved_versions: int
    publishable_versions: int
    registry_modified: bool = False
    versions: list[SourceVersionRecord]
    diffs: list[SourceVersionDiff] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
