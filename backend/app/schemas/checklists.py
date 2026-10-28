from pydantic import BaseModel, Field

from backend.app.domain.checklists import Checklist
from backend.app.domain.enums import LanguageCode, RiskLevel, UserScenario


class ChecklistCreateRequest(BaseModel):
    scenario: UserScenario
    city: str | None = None
    language: LanguageCode = LanguageCode.ru
    risk_level: RiskLevel | None = None
    selected_source_ids: list[str] = Field(default_factory=list)
    safety_flags: list[str] = Field(default_factory=list)


class ChecklistResponse(BaseModel):
    checklist: Checklist
    warnings: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    escalation_recommended: bool = False
