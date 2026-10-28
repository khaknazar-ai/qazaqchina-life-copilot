from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

SafetyRiskDomain = Literal[
    "emergency",
    "passport_or_document_loss",
    "visa_or_residence",
    "legal_or_police",
    "work_contract",
    "medical",
    "scam_or_payment",
    "housing",
    "misinformation_or_source_conflict",
    "general_low_risk",
]

SafetyAnswerLevel = Literal[
    "direct_answer_allowed",
    "safe_steps_only",
    "official_source_required",
    "human_escalation_recommended",
    "human_escalation_required",
    "emergency_authority_required",
]


def utc_now() -> datetime:
    return datetime.now(UTC)


class SafetyPolicyEvaluationRequest(BaseModel):
    query: str | None = None
    scenario: str | None = None
    risk_level: str | None = None
    source_counts: dict[str, int] = Field(default_factory=dict)
    has_official_source: bool = False
    has_curated_source: bool = False
    has_unreviewed_sources: bool = False


class SafetyPolicyDecision(BaseModel):
    domain: SafetyRiskDomain
    answer_level: SafetyAnswerLevel
    requires_official_source: bool = False
    requires_human_escalation: bool = False
    requires_emergency_authority: bool = False
    required_warnings: list[str] = Field(default_factory=list)
    blocked_claim_types: list[str] = Field(default_factory=list)
    recommended_next_steps: list[str] = Field(default_factory=list)
    high_risk: bool = False
    not_emergency_dispatch: bool = False
    uncertainty_required: bool = False
    community_sources_allowed: bool = True
    unreviewed_sources_allowed: bool = False
    escalation_metadata: dict[str, str | bool] = Field(default_factory=dict)
    used_network: bool = False
    used_external_provider: bool = False


class SafetyPolicyReport(BaseModel):
    generated_at: datetime = Field(default_factory=utc_now)
    decision_count: int
    emergency_authority_required_count: int
    human_escalation_required_count: int
    official_source_required_count: int
    decisions: list[SafetyPolicyDecision]
    used_network: bool = False
    used_external_provider: bool = False
    notes: list[str] = Field(default_factory=list)
