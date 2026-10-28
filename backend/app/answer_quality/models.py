from pydantic import BaseModel, Field


class AnswerSourceNote(BaseModel):
    source_id: str
    title: str
    source_type: str | None = None
    trust_level: str | None = None
    used_for: str = "grounding"
    warning: str | None = None
    url: str | None = None
    publisher: str | None = None
    date_accessed: str | None = None
    last_reviewed_at: str | None = None
    is_synthetic: bool = False
    moderation_status: str | None = None
    status_override: str | None = None
    allow_ai_retrieval: bool = True
    content_hash: str | None = None


class GroundedAnswerSection(BaseModel):
    heading: str
    body: str
    source_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ReviewedAnswerNote(BaseModel):
    conflict_id: str
    revision: int
    note: str
    source_ids: list[str] = Field(default_factory=list)
    snapshot_refs: dict[str, str] = Field(default_factory=dict)
    valid_until: str


class GroundedAnswerDraft(BaseModel):
    scenario: str | None = None
    risk_level: str | None = None
    language: str | None = None
    direct_answer: str
    grounded_facts: list[GroundedAnswerSection] = Field(default_factory=list)
    recommended_steps: list[GroundedAnswerSection] = Field(default_factory=list)
    checklist_items: list[str] = Field(default_factory=list)
    escalation: list[str] = Field(default_factory=list)
    uncertainty: list[str] = Field(default_factory=list)
    source_notes: list[AnswerSourceNote] = Field(default_factory=list)
    reviewed_notes: list[ReviewedAnswerNote] = Field(default_factory=list)
    unreviewed_candidate_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class AnswerQualityIssue(BaseModel):
    severity: str
    code: str
    message: str


class AnswerQualityReport(BaseModel):
    scenario: str | None = None
    risk_level: str | None = None
    has_direct_answer: bool
    has_grounded_facts: bool
    has_steps: bool
    has_escalation: bool
    has_uncertainty: bool
    trusted_source_count: int
    unreviewed_candidate_count: int = 0
    issues: list[AnswerQualityIssue] = Field(default_factory=list)
