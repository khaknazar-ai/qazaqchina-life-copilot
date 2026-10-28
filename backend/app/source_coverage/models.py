from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

SourceCoverageTrustTier = Literal[
    "official_law",
    "official_regulation",
    "official_policy_document",
    "official_agency_page",
    "official_consulate_or_embassy_page",
    "official_university_page",
    "curated_official_backed_guide",
    "verified_consular_comment",
    "verified_professional_comment",
    "community_experience",
    "unknown_or_unclassified",
]

CoverageStatus = Literal[
    "covered_by_official",
    "covered_by_curated_official_backed",
    "supported_by_verified_comment",
    "community_only",
    "missing",
    "stale_or_unknown",
    "refresh_required",
]

CoveragePriority = Literal["critical", "high", "medium", "low"]


def utc_now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class SourceCoverageRequirement(BaseModel):
    domain: str
    required_trust_tiers: list[SourceCoverageTrustTier]
    minimum_status: CoverageStatus
    priority: CoveragePriority
    reason: str
    high_risk: bool = False


class SourceCoverageItem(BaseModel):
    domain: str
    source_id: str | None = None
    source_title: str | None = None
    trust_tier: SourceCoverageTrustTier
    freshness_status: str | None = None
    source_version_status: str | None = None
    verified_role: str | None = None
    is_official: bool = False
    is_verified_comment: bool = False
    is_community: bool = False
    eligible_for_readiness: bool = True
    notes: list[str] = Field(default_factory=list)


class CoverageGap(BaseModel):
    domain: str
    status: CoverageStatus
    priority: CoveragePriority
    missing_trust_tiers: list[SourceCoverageTrustTier]
    risk: str
    recommended_action: str
    can_answer_without_official_source: bool
    requires_human_review: bool = False


class SourceAcquisitionTask(BaseModel):
    task_id: str
    domain: str
    priority: CoveragePriority
    target_trust_tier: SourceCoverageTrustTier
    description: str
    suggested_owner_role: str
    acceptance_criteria: list[str]
    not_trusted_until_reviewed: bool = True


class SourceCoverageReport(BaseModel):
    generated_at: datetime = Field(default_factory=utc_now)
    total_domains: int
    covered_by_official_count: int
    curated_count: int
    verified_comment_count: int
    community_only_count: int
    missing_count: int
    refresh_required_count: int
    critical_gap_count: int
    requirements: list[SourceCoverageRequirement]
    coverage_items: list[SourceCoverageItem]
    gaps: list[CoverageGap]
    acquisition_backlog: list[SourceAcquisitionTask]
    used_network: bool = False
    used_external_provider: bool = False
    notes: list[str] = Field(default_factory=list)

    @field_validator("generated_at")
    @classmethod
    def _generated_at_must_be_utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value)
