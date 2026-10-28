from datetime import datetime

from pydantic import BaseModel, Field

from backend.app.domain.checklists import Checklist
from backend.app.domain.enums import CaseStatus, EscalationReason, RiskLevel, UserScenario
from backend.app.domain.sources import SourceReference


class UserCase(BaseModel):
    case_id: str
    user_id: str | None = None
    case_type: UserScenario
    city: str | None = None
    risk_level: RiskLevel = RiskLevel.normal
    status: CaseStatus = CaseStatus.open
    checklists: list[Checklist] = Field(default_factory=list)
    sources: list[SourceReference] = Field(default_factory=list)
    escalation_required: bool = False
    escalation_reasons: list[EscalationReason] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
