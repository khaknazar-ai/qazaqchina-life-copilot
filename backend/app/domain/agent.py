from pydantic import BaseModel, Field

from backend.app.domain.checklists import Checklist
from backend.app.domain.enums import EscalationReason, LanguageCode, RiskLevel, UserScenario
from backend.app.domain.sources import Citation, RetrievedSource, SourceConflict


class UserProfileSnapshot(BaseModel):
    user_id: str | None = None
    city: str | None = None
    nationality: str | None = None
    preferred_language: LanguageCode = LanguageCode.ru


class AgentState(BaseModel):
    trace_id: str
    user_id: str | None = None
    session_id: str | None = None
    user_message: str
    preferred_language: LanguageCode | None = None
    city: str | None = None
    followup_scenario: UserScenario | None = None
    followup_risk_level: RiskLevel | None = None
    detected_language: LanguageCode = LanguageCode.unknown
    response_language: LanguageCode = LanguageCode.ru
    user_profile: UserProfileSnapshot | None = None
    scenario: UserScenario = UserScenario.unclear
    risk_level: RiskLevel = RiskLevel.normal
    missing_information: list[str] = Field(default_factory=list)
    selected_sources: list[RetrievedSource] = Field(default_factory=list)
    source_conflicts: list[SourceConflict] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    escalation_required: bool = False
    escalation_reasons: list[EscalationReason] = Field(default_factory=list)
    escalation_summary: str | None = None
    checklist: Checklist | None = None
    draft_answer: str | None = None
    final_answer: str | None = None
    safety_flags: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    tool_decision: dict | None = None
    tool_trace: dict | None = None
    unreviewed_source_candidate_count: int = 0
    grounded_answer: dict | None = None
    answer_quality_report: dict | None = None
    answer_verification_report: dict | None = None
    hybrid_rag_result: dict | None = None
