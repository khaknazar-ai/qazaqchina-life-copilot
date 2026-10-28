from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

AIResponseMode = Literal[
    "refuse_high_risk_claim",
    "uncertainty_only",
    "safe_general_steps_only",
    "human_escalation_required",
    "official_verification_required",
]

ClosureStatus = Literal[
    "open",
    "blocked_waiting_official_source",
    "needs_review",
    "ready_for_source_candidate",
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


class OfficialSourceNeed(BaseModel):
    need_id: str
    domain: str
    required_trust_tier: str
    description: str
    why_required: str
    blocks_claim_types: list[str] = Field(default_factory=list)
    can_be_replaced_by_consular_comment: bool = False


class ConsularCommentSupportPlan(BaseModel):
    domain: str
    useful_roles: list[str]
    purpose: str
    limitations: list[str]
    cannot_replace_official_source: bool = True


class CuratedGuideReadiness(BaseModel):
    domain: str
    guide_allowed_now: bool
    required_before_publish: list[str]
    warning: str


class AIResponseConstraint(BaseModel):
    domain: str
    allowed_response_mode: AIResponseMode
    prohibited_claims: list[str]
    required_user_warning: str
    escalation_recommendation: str | None = None


class CriticalGapClosurePlan(BaseModel):
    domain: str
    priority: str
    current_status: str
    risk: str
    official_source_needs: list[OfficialSourceNeed]
    consular_comment_support: ConsularCommentSupportPlan | None = None
    curated_guide_readiness: CuratedGuideReadiness
    ai_response_constraint: AIResponseConstraint
    acquisition_task_ids: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str]
    closure_status: ClosureStatus
    can_close_without_official_source: bool = False
    notes: list[str] = Field(default_factory=list)


class CriticalSourceGapClosureReport(BaseModel):
    generated_at: datetime = Field(default_factory=utc_now)
    total_critical_gaps: int
    open_gap_count: int
    blocked_gap_count: int
    ready_for_candidate_count: int
    closed_gap_count: int
    plans: list[CriticalGapClosurePlan]
    global_ai_constraints: list[str]
    source_acquisition_backlog_links: list[str]
    not_trusted_evidence_warning: str
    ready_for_closed_beta: bool = False
    ready_for_public_launch: bool = False
    used_network: bool = False
    used_external_provider: bool = False
    notes: list[str] = Field(default_factory=list)

    @field_validator("generated_at")
    @classmethod
    def _generated_at_must_be_utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value)
