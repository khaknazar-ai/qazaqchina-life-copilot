from typing import Any

from pydantic import BaseModel, Field, StrictBool, model_validator

from backend.app.domain.enums import LanguageCode, RiskLevel, UserScenario
from backend.app.domain.sources import Citation
from backend.app.source_conflicts.models import ResolutionApplicability, canonical_scope


class ChatRequest(BaseModel):
    user_message: str = Field(min_length=1, max_length=8000)
    user_id: str | None = Field(default=None, min_length=1, max_length=128)
    session_id: str | None = Field(default=None, min_length=1, max_length=128)
    city: str | None = Field(default=None, max_length=100)
    preferred_language: LanguageCode = LanguageCode.ru
    reset_context: bool = False
    # None retains explicit saved-case selection; fresh profile use requires True.
    use_saved_context: StrictBool | None = None
    # Current chat continuity is separate from opting into profile/saved-case data.
    use_conversation_context: StrictBool = False
    case_id: str | None = Field(default=None, min_length=1, max_length=80)
    source_applicability: ResolutionApplicability | None = None

    @model_validator(mode="after")
    def consistent_city(self) -> "ChatRequest":
        scoped_city = self.source_applicability.city if self.source_applicability else None
        if (
            self.city
            and scoped_city
            and canonical_scope("city", self.city)
            != canonical_scope(
                "city",
                scoped_city,
            )
        ):
            raise ValueError("City and source applicability city must refer to the same place")
        if not self.city and scoped_city:
            self.city = scoped_city
        return self


class ChatResponse(BaseModel):
    trace_id: str
    session_id: str | None = None
    case_id: str | None = None
    scenario: UserScenario
    risk_level: RiskLevel
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    escalation_required: bool = False
    safety_flags: list[str] = Field(default_factory=list)
    grounded_answer: dict[str, Any] | None = None
    answer_quality_report: dict[str, Any] | None = None
    answer_verification_report: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    safety_policy_decision: dict[str, Any] | None = None
    high_risk: bool = False
    requires_official_source: bool = False
    requires_human_escalation: bool = False
    requires_emergency_authority: bool = False
    not_emergency_dispatch: bool = False
    required_warnings: list[str] = Field(default_factory=list)
    recommended_next_steps: list[str] = Field(default_factory=list)
    escalation_recommended: bool = False
    escalation_prefill: dict[str, Any] | None = None
    has_source_review_constraints: bool = False
    source_review_constraint: dict[str, Any] | None = None
    required_official_verification_warning: str | None = None
    prohibited_claim_types: list[str] = Field(default_factory=list)
    citizen_visible_source_review_disclosure_allowed: bool = False
