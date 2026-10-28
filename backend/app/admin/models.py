from enum import StrEnum

from pydantic import BaseModel, Field

from backend.app.domain.community import CommunityPost, ContributorProfile


class AdminDecisionAction(StrEnum):
    approve = "approve"
    reject = "reject"
    flag = "flag"
    request_changes = "request_changes"
    revoke = "revoke"
    expire = "expire"
    no_action = "no_action"


class AdminReviewType(StrEnum):
    community_post = "community_post"
    role_verification = "role_verification"
    source_conflict = "source_conflict"
    citation_issue = "citation_issue"
    source_registry_record = "source_registry_record"


class AdminDecision(BaseModel):
    review_type: AdminReviewType
    action: AdminDecisionAction
    admin_id: str
    target_id: str
    reason: str | None = None
    notes: str | None = None


class AdminReviewResult(BaseModel):
    review_type: str
    target_id: str
    action: str
    changed: bool
    message: str
    warnings: list[str] = Field(default_factory=list)


class CommunityModerationAdminResult(BaseModel):
    post: CommunityPost
    decision: AdminDecision
    message: str


class RoleVerificationAdminResult(BaseModel):
    contributor: ContributorProfile
    decision: AdminDecision
    message: str


class SourceGovernanceAdminResult(BaseModel):
    decision: AdminDecision
    message: str
    recommended_actions: list[str] = Field(default_factory=list)
