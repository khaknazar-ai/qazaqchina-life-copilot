from typing import Literal

from pydantic import BaseModel, Field

from backend.app.domain.community import ContributorProfile
from backend.app.domain.enums import VerifiedContributorRole


class VerificationIssue(BaseModel):
    severity: str
    code: str
    message: str
    source_id: str | None = None
    suggested_action: str | None = None


class AnswerVerificationRequest(BaseModel):
    answer_text: str
    scenario: str | None = None
    risk_level: str | None = None
    domain: str | None = None
    evidence: list[dict] = Field(default_factory=list)
    source_notes: list[dict] = Field(default_factory=list)
    unreviewed_candidate_count: int = 0
    coverage_warnings: list[str] = Field(default_factory=list)


class AnswerVerificationReport(BaseModel):
    passed: bool
    max_severity: str
    scenario: str | None = None
    risk_level: str | None = None
    domain: str | None = None
    evidence_count: int
    trusted_source_count: int
    source_note_count: int
    unreviewed_candidate_count: int
    unsupported_claim_count: int = 0
    issues: list[VerificationIssue] = Field(default_factory=list)


class RoleVerificationRequest(BaseModel):
    contributor_id: str
    requested_role: VerifiedContributorRole
    self_declared_role: str | None = None
    institution_name: str | None = None
    evidence_summary: str | None = None
    requested_by_user_id: str | None = None


class RoleVerificationDecision(BaseModel):
    contributor_id: str
    requested_role: VerifiedContributorRole
    decision: Literal["approved", "rejected", "revoked", "expired"]
    decided_by_admin_id: str
    reason: str | None = None


class RoleVerificationResult(BaseModel):
    contributor: ContributorProfile
    message: str
    changed: bool
