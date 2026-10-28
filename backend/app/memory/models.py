from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


class MemoryRetentionPolicy(BaseModel):
    max_turns: int = 8
    # Keep a complete accepted chat question (after redaction), not its preview.
    max_text_chars: int = 8000
    max_source_notes: int = 5
    max_evidence_items: int = 5
    persist_raw_messages: bool = False
    redact_sensitive_data: bool = True


class ConversationTurn(BaseModel):
    role: str
    text: str
    created_at: datetime = Field(default_factory=utc_now)
    scenario: str | None = None
    risk_level: str | None = None
    language: str | None = None
    redacted: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class TrustedSourceMemory(BaseModel):
    source_id: str
    title: str
    source_type: str | None = None
    trust_level: str | None = None
    used_for: str = "grounding"


class EvidenceMemorySummary(BaseModel):
    domain: str | None = None
    evidence_count: int = 0
    official_count: int = 0
    curated_count: int = 0
    community_count: int = 0
    has_official_or_curated: bool = False
    source_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AnswerVerificationMemory(BaseModel):
    passed: bool | None = None
    max_severity: str | None = None
    issue_count: int = 0
    unsupported_claim_count: int = 0


class ChecklistProgressMemory(BaseModel):
    checklist_id: str | None = None
    completed_items: list[str] = Field(default_factory=list)
    pending_items: list[str] = Field(default_factory=list)


class SessionMemory(BaseModel):
    session_id: str
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    active_scenario: str | None = None
    active_risk_level: str | None = None
    preferred_language: str | None = None
    city: str | None = None
    recent_turns: list[ConversationTurn] = Field(default_factory=list)
    last_trusted_sources: list[TrustedSourceMemory] = Field(default_factory=list)
    last_evidence_summary: EvidenceMemorySummary | None = None
    last_answer_verification: AnswerVerificationMemory | None = None
    checklist_progress: ChecklistProgressMemory | None = None
    last_escalation_required: bool = False
    safety_warnings: list[str] = Field(default_factory=list)
    retention_policy: MemoryRetentionPolicy = Field(default_factory=MemoryRetentionPolicy)


class ContextMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: str
    truncated: bool = False


class FollowUpContext(BaseModel):
    session_id: str
    active_scenario: str | None = None
    active_risk_level: str | None = None
    preferred_language: str | None = None
    city: str | None = None
    recent_summary: str
    recent_messages: list[ContextMessage] = Field(default_factory=list)
    history_truncated: bool = False
    trusted_source_ids: list[str] = Field(default_factory=list)
    evidence_summary: EvidenceMemorySummary | None = None
    checklist_progress: ChecklistProgressMemory | None = None
    warnings: list[str] = Field(default_factory=list)
    # Server-loaded case/profile fields remain user material, never source evidence.
    task_context: dict[str, str] = Field(default_factory=dict)
