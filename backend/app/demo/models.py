from pydantic import BaseModel, Field

from backend.app.domain.enums import LanguageCode, RiskLevel, UserScenario


class DemoScenario(BaseModel):
    scenario_id: str
    title: str
    description: str
    user_message: str
    category: UserScenario
    expected_features: list[str] = Field(default_factory=list)
    preferred_language: LanguageCode | None = None
    risk_hint: RiskLevel | None = None


class DemoRunRequest(BaseModel):
    scenario_id: str
    use_agent_workflow: bool = True


class DemoRunResult(BaseModel):
    scenario: DemoScenario
    chat_response: dict | None = None
    checklist: dict | None = None
    translation_explanation: dict | None = None
    moderation_result: dict | None = None
    escalation_summary: str | None = None
    source_ids: list[str] = Field(default_factory=list)
    safety_flags: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
