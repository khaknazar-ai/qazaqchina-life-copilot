from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

SourceReviewAnswerConstraintMode = Literal[
    "direct_answer_allowed",
    "cautious_general_steps_only",
    "official_verification_required",
    "human_escalation_recommended",
    "refuse_high_risk_specific_claims",
]


def utc_now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class SourceReviewAnswerConstraint(BaseModel):
    domain: str
    source_review_status: str
    official_source_published: bool
    publish_preview_eligible: bool
    candidate_count: int
    blocked_candidate_count: int
    allowed_mode: SourceReviewAnswerConstraintMode
    prohibited_claim_types: list[str] = Field(default_factory=list)
    required_warning: str
    safe_response_guidance: list[str] = Field(default_factory=list)
    citizen_visible_source_review_disclosure_allowed: bool = False
    admin_only_notes: list[str] = Field(default_factory=list)


class SourceReviewAnswerConstraintsReport(BaseModel):
    generated_at: datetime = Field(default_factory=utc_now)
    total_domains: int
    constrained_domain_count: int
    direct_answer_allowed_count: int
    official_verification_required_count: int
    human_escalation_recommended_count: int
    refuse_specific_claims_count: int
    constraints: list[SourceReviewAnswerConstraint]
    ready_for_closed_beta: bool = False
    ready_for_public_launch: bool = False
    used_network: bool = False
    used_external_provider: bool = False
    notes: list[str] = Field(default_factory=list)

    @field_validator("generated_at")
    @classmethod
    def _generated_at_must_be_utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value)
