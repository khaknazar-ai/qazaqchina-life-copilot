from pydantic import BaseModel, Field

from backend.app.domain.enums import RiskLevel, UserScenario


class EscalationTrigger(BaseModel):
    trigger_type: str
    severity: str
    reason: str
    recommended_action: str
    source: str | None = None


class EscalationPlan(BaseModel):
    escalation_required: bool
    requires_human_review: bool
    priority: str
    triggers: list[EscalationTrigger] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    handoff_summary: str | None = None


class CaseDraft(BaseModel):
    user_id: str | None = None
    session_id: str | None = None
    scenario: UserScenario
    risk_level: RiskLevel
    title: str
    summary: str
    priority: str
    escalation_reasons: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    safety_flags: list[str] = Field(default_factory=list)
