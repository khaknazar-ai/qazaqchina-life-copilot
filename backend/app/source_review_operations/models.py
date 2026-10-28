from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

ActionPriority = Literal["critical", "high", "medium", "low"]


def utc_now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class SourceReviewOperationAction(BaseModel):
    action_id: str
    priority: ActionPriority
    domain: str | None
    candidate_id: str | None
    title: str
    description: str
    owner_role: str
    blocks_publish_preview: bool = True
    blocks_citizen_direct_answer: bool = True


class SourceReviewOperationCandidateStatus(BaseModel):
    candidate_id: str
    domain: str
    proposed_trust_tier: str
    intake_ready: bool
    review_evidence_present: bool
    reviewer_packet_available: bool
    publish_preview_eligible: bool
    published: bool = False
    trusted_for_citizen_answers: bool = False
    answer_constraint_mode: str | None = None
    citizen_visible_source_disclosure_allowed: bool = False
    blocker_count: int
    next_required_actions: list[SourceReviewOperationAction]
    admin_only_notes: list[str] = Field(default_factory=list)


class SourceReviewOperationsDashboardReport(BaseModel):
    generated_at: datetime = Field(default_factory=utc_now)
    total_candidates: int
    total_domains: int
    blocked_candidate_count: int
    publish_preview_eligible_count: int
    published_count: int
    trusted_for_citizen_answers_count: int
    constrained_domain_count: int
    critical_action_count: int
    high_action_count: int
    operator_ready_count: int
    ready_for_closed_beta: bool = False
    ready_for_public_launch: bool = False
    used_network: bool = False
    used_external_provider: bool = False
    candidate_statuses: list[SourceReviewOperationCandidateStatus]
    actions: list[SourceReviewOperationAction]
    notes: list[str] = Field(default_factory=list)

    @field_validator("generated_at")
    @classmethod
    def _generated_at_must_be_utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value)
