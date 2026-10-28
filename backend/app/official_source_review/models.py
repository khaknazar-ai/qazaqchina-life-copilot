from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

OfficialSourceCandidateStatus = Literal[
    "draft",
    "submitted",
    "in_review",
    "changes_requested",
    "rejected",
    "blocked_needs_official_evidence",
    "approved_for_publish_preview",
    "published",
]

OfficialSourceReviewDecision = Literal[
    "pending",
    "needs_changes",
    "rejected",
    "approved_for_preview",
    "approved_for_publishing",
]


def utc_now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class OfficialSourceCandidate(BaseModel):
    candidate_id: str
    domain: str
    source_title: str | None = None
    source_url: str | None = None
    source_document_ref: str | None = None
    proposed_trust_tier: str
    claimed_publisher: str | None = None
    jurisdiction_or_scope: str | None = None
    language: str | None = None
    related_gap_id: str | None = None
    related_acquisition_task_id: str | None = None
    status: OfficialSourceCandidateStatus = "draft"
    not_trusted_until_approved: bool = True
    notes: list[str] = Field(default_factory=list)


class OfficialSourceReviewChecklist(BaseModel):
    candidate_id: str
    official_publisher_verified: bool = False
    url_or_document_captured: bool = False
    trust_tier_classified: bool = False
    domain_scope_confirmed: bool = False
    freshness_checked: bool = False
    source_version_recorded: bool = False
    no_conflict_with_existing_sources: bool = False
    high_risk_second_review_required: bool = True
    reviewer_notes_present: bool = False
    prohibited_if_missing: list[str] = Field(default_factory=list)


class OfficialSourceReviewRecord(BaseModel):
    review_id: str
    candidate_id: str
    reviewer_role: str
    decision: OfficialSourceReviewDecision
    checklist: OfficialSourceReviewChecklist
    allowed_claim_types: list[str] = Field(default_factory=list)
    prohibited_claim_types: list[str] = Field(default_factory=list)
    required_warnings: list[str] = Field(default_factory=list)
    review_notes: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @field_validator("created_at", "updated_at")
    @classmethod
    def _timestamps_must_be_utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value)


class OfficialSourceReviewSummary(BaseModel):
    generated_at: datetime = Field(default_factory=utc_now)
    total_candidates: int
    draft_count: int
    blocked_count: int
    approved_for_preview_count: int
    published_count: int
    critical_gap_candidate_count: int
    not_trusted_candidate_count: int
    review_records: list[OfficialSourceReviewRecord]
    candidates: list[OfficialSourceCandidate]
    ready_for_closed_beta: bool = False
    ready_for_public_launch: bool = False
    used_network: bool = False
    used_external_provider: bool = False
    notes: list[str] = Field(default_factory=list)

    @field_validator("generated_at")
    @classmethod
    def _generated_at_must_be_utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value)
