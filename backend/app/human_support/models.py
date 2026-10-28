from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

FeedbackCategory = Literal[
    "answer_helpful",
    "answer_wrong",
    "outdated_info",
    "unsafe_advice",
    "source_problem",
    "app_problem",
    "other",
]
FeedbackSeverity = Literal["low", "normal", "high", "urgent"]
EscalationReason = Literal[
    "needs_human_help",
    "emergency",
    "legal_or_visa_risk",
    "medical_risk",
    "scam_or_payment_risk",
    "source_conflict",
    "other",
]
EscalationUrgency = Literal["normal", "high", "urgent"]
QueueStatus = Literal[
    "new",
    "in_review",
    "waiting_for_user",
    "resolved",
    "closed",
    "escalated",
]


def utc_now() -> datetime:
    return datetime.now(UTC)


class CitizenFeedbackCreateRequest(BaseModel):
    user_id: str | None = None
    session_id: str | None = None
    category: FeedbackCategory
    message: str
    severity: FeedbackSeverity = "normal"
    scenario: str | None = None
    risk_level: str | None = None
    related_turn_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CitizenFeedbackResponse(BaseModel):
    feedback_id: str = Field(default_factory=lambda: f"feedback-{uuid4().hex}")
    status: str
    created_at: datetime
    safety_message: str
    stored: bool


class EscalationCreateRequest(BaseModel):
    user_id: str | None = None
    session_id: str | None = None
    scenario: str | None = None
    risk_level: str | None = None
    summary: str
    reason: EscalationReason
    urgency: EscalationUrgency = "normal"
    related_turn_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EscalationResponse(BaseModel):
    escalation_id: str = Field(default_factory=lambda: f"escalation-{uuid4().hex}")
    status: str
    created_at: datetime
    safety_message: str
    not_emergency_dispatch: bool = True
    stored: bool


class AdminQueueUpdateRequest(BaseModel):
    status: QueueStatus
    assigned_to: str | None = None
    note: str | None = None


class HumanSupportSummary(BaseModel):
    feedback_count: int
    escalation_count: int
    urgent_escalation_count: int
    open_feedback_count: int
    open_escalation_count: int
    used_network: bool = False
    used_external_provider: bool = False
    warnings: list[str] = Field(default_factory=list)
