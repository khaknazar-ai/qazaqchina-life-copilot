from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from backend.app.domain.agent import UserProfileSnapshot
from backend.app.domain.checklists import Checklist, ChecklistGroup
from backend.app.domain.enums import LanguageCode, RiskLevel, UserScenario


class ChecklistTemplateItem(BaseModel):
    item_id: str
    title: str
    description: str | None = None
    required: bool = True
    risk_note: str | None = None
    source_required: bool = False
    escalation_relevant: bool = False
    tags: list[str] = Field(default_factory=list)
    group: ChecklistGroup = "optional"
    required_documents: list[str] = Field(default_factory=list)
    estimated_time: str | None = None


class ChecklistProfileContext(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    city: str | None = Field(default=None, max_length=100)
    purpose: str | None = Field(default=None, max_length=300)
    institution: str | None = Field(default=None, max_length=200)
    deadline: date | None = None


class ChecklistGenerationRequest(BaseModel):
    scenario: UserScenario
    risk_level: RiskLevel = RiskLevel.normal
    language: LanguageCode = LanguageCode.ru
    user_profile: UserProfileSnapshot | None = None
    selected_source_ids: list[str] = Field(default_factory=list)
    safety_flags: list[str] = Field(default_factory=list)
    approved_context: ChecklistProfileContext | None = None
    preparation_only: bool = False


class ChecklistGenerationResult(BaseModel):
    checklist: Checklist
    warnings: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    escalation_recommended: bool = False
