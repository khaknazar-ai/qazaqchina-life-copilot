from pydantic import BaseModel, Field

from backend.app.domain.enums import LanguageCode, RiskLevel


class EmergencyHelpRequest(BaseModel):
    user_message: str = Field(min_length=1, max_length=8000)
    city: str | None = Field(default=None, max_length=100)
    language: LanguageCode = LanguageCode.ru


class EmergencyHelpResponse(BaseModel):
    trace_id: str
    emergency_type: str
    risk_level: RiskLevel
    immediate_steps: list[str]
    chinese_phrase: str | None = None
    escalation_required: bool = True
    disclaimer: str
    not_emergency_dispatch: bool = True
    contacts_status: str = "not_configured"
    used_network: bool = False
