from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

SourceFreshnessStatus = Literal[
    "fresh",
    "unknown",
    "stale",
    "deprecated",
    "needs_refresh",
]


def utc_now() -> datetime:
    return datetime.now(UTC)


class SourceFreshnessPolicy(BaseModel):
    source_type: str | None = None
    trust_level: str | None = None
    default_max_age_days: int | None = None
    high_risk_max_age_days: int | None = None
    require_reviewed_at: bool = False
    notes: list[str] = Field(default_factory=list)


class SourceFreshnessMetadata(BaseModel):
    source_id: str
    url: str | None = None
    collected_at: datetime | None = None
    last_reviewed_at: datetime | None = None
    expires_at: datetime | None = None
    content_hash: str | None = None
    freshness_note: str | None = None
    status_override: str | None = None


class SourceFreshnessAssessment(BaseModel):
    source_id: str
    title: str | None = None
    source_type: str | None = None
    trust_level: str | None = None
    status: SourceFreshnessStatus
    age_days: int | None = None
    max_age_days: int | None = None
    needs_refresh: bool = False
    high_risk_context: bool = False
    warnings: list[str] = Field(default_factory=list)
    recommended_action: str | None = None


class SourceFreshnessReport(BaseModel):
    generated_at: datetime = Field(default_factory=utc_now)
    total_sources: int
    fresh_count: int
    unknown_count: int
    stale_count: int
    deprecated_count: int
    needs_refresh_count: int
    assessments: list[SourceFreshnessAssessment]
    warnings: list[str] = Field(default_factory=list)
