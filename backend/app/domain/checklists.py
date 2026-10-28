from typing import Literal

from pydantic import BaseModel, Field

from backend.app.domain.enums import ChecklistItemStatus, LanguageCode, RiskLevel, UserScenario

ChecklistGroup = Literal["before_arrival", "after_arrival", "first_week", "urgent", "optional"]


class ChecklistItem(BaseModel):
    item_id: str
    title: str
    description: str | None = None
    priority: int = 3
    scenario: UserScenario
    risk_level: RiskLevel = RiskLevel.normal
    required_documents: list[str] = Field(default_factory=list)
    estimated_time: str | None = None
    source_ids: list[str] = Field(default_factory=list)
    community_source_ids: list[str] = Field(default_factory=list)
    status: ChecklistItemStatus = ChecklistItemStatus.not_started
    group: ChecklistGroup = "optional"
    action: Literal["chat", "explain", "support"] = "chat"


class Checklist(BaseModel):
    checklist_id: str
    title: str
    scenario: UserScenario
    language: LanguageCode = LanguageCode.ru
    items: list[ChecklistItem] = Field(default_factory=list)
