from pydantic import BaseModel, Field

from backend.app.domain.enums import ModerationStatus


class ModerationFinding(BaseModel):
    finding_type: str
    severity: str
    summary: str
    matched_terms: list[str] = Field(default_factory=list)


class ModerationResult(BaseModel):
    status_recommendation: ModerationStatus
    allow_ai_retrieval_recommendation: bool
    findings: list[ModerationFinding] = Field(default_factory=list)
    needs_admin_review: bool = False
    review_reasons: list[str] = Field(default_factory=list)
