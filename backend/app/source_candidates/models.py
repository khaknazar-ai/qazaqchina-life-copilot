from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

SourceCandidateStatus = Literal["pending", "needs_review", "approved", "rejected"]
SourceCandidateReviewAction = Literal["approve", "reject", "needs_review"]


def utc_now() -> datetime:
    return datetime.now(UTC)


class SourceCandidate(BaseModel):
    candidate_id: str
    title: str
    url: str
    snippet: str
    domain: str | None = None
    source_type_guess: str | None = None
    trust_guess: str | None = None
    language: str | None = None
    country: str | None = "CN"
    city: str | None = None
    scenario: str | None = None
    risk_level: str | None = None
    official_domain_hint: bool = False
    requires_review: bool = True
    status: SourceCandidateStatus = "pending"
    warnings: list[str] = Field(default_factory=list)
    review_notes: list[str] = Field(default_factory=list)
    discovered_by: str = "offline_tool_contract"
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime | None = None
    assigned_source_type: str | None = None
    assigned_trust_level: str | None = None
    allow_retrieval: bool = False
    freshness_note: str | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None


class SourceCandidateReviewDecision(BaseModel):
    candidate_id: str
    action: SourceCandidateReviewAction
    reviewer_id: str
    reason: str
    assigned_source_type: str | None = None
    assigned_trust_level: str | None = None
    allow_retrieval: bool = False
    freshness_note: str | None = None
    notes: str | None = None


class SourceCandidateReviewResult(BaseModel):
    candidate: SourceCandidate
    decision: SourceCandidateReviewDecision
    changed: bool
    warnings: list[str] = Field(default_factory=list)


class RegistryReadySource(BaseModel):
    candidate_id: str
    title: str
    url: str
    source_type: str
    trust_level: str
    language: str | None = None
    country: str | None = "CN"
    city: str | None = None
    allow_retrieval: bool
    freshness_note: str | None = None
    excerpt: str
    warnings: list[str] = Field(default_factory=list)
