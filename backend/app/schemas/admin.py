from pydantic import BaseModel, Field

from backend.app.admin.models import (
    AdminDecision,
    CommunityModerationAdminResult,
    RoleVerificationAdminResult,
    SourceGovernanceAdminResult,
)
from backend.app.domain.community import CommunityPost, ContributorProfile
from backend.app.domain.enums import VerifiedContributorRole
from backend.app.source_candidates.models import (
    RegistryReadySource,
    SourceCandidate,
    SourceCandidateReviewAction,
)
from backend.app.source_ingestion.models import (
    SourceIngestionRecord,
    SourceIngestionValidationIssue,
)
from backend.app.source_publishing.models import SourcePublishRequest
from backend.app.source_versioning.models import SourceVersionRecord


class CommunityPostAdminReviewRequest(BaseModel):
    post: CommunityPost
    decision: AdminDecision


class CommunityPostAdminReviewResponse(BaseModel):
    result: CommunityModerationAdminResult


class RoleVerificationAdminReviewRequest(BaseModel):
    contributor: ContributorProfile
    requested_role: VerifiedContributorRole
    decision: AdminDecision


class RoleVerificationAdminReviewResponse(BaseModel):
    result: RoleVerificationAdminResult


class SourceGovernanceAdminReviewRequest(BaseModel):
    decision: AdminDecision
    recommended_actions: list[str] = Field(default_factory=list)


class SourceGovernanceAdminReviewResponse(BaseModel):
    result: SourceGovernanceAdminResult


class SourceCandidateCreateRequest(BaseModel):
    title: str
    url: str
    snippet: str
    source_type_guess: str | None = None
    trust_guess: str | None = None
    language: str | None = None
    country: str = "CN"
    city: str | None = None
    scenario: str | None = None
    risk_level: str | None = None
    official_domain_hint: bool = False
    warnings: list[str] = Field(default_factory=list)


class SourceCandidateReviewRequest(BaseModel):
    action: SourceCandidateReviewAction
    reviewer_id: str
    reason: str
    assigned_source_type: str | None = None
    assigned_trust_level: str | None = None
    allow_retrieval: bool = False
    freshness_note: str | None = None
    notes: str | None = None


class AdminURLPreviewRequest(BaseModel):
    url: str
    scenario: str | None = None
    risk_level: str | None = None
    language: str | None = None
    city: str | None = None
    allow_network: bool = False
    confirm_network: bool = False


class AdminURLPreviewResponse(BaseModel):
    used_network: bool
    fetched: bool
    candidate_created: bool
    candidate: dict | None = None
    fetch_result: dict
    warnings: list[str] = Field(default_factory=list)
    message: str


class SourceCandidateListResponse(BaseModel):
    candidates: list[SourceCandidate]
    total: int
    warnings: list[str] = Field(default_factory=list)


class SourceCandidateReviewResponse(BaseModel):
    candidate: SourceCandidate
    changed: bool
    warnings: list[str] = Field(default_factory=list)
    demo_warning: str = "admin_auth_not_implemented_demo_only"


class SourceVersionCreateRequest(BaseModel):
    reviewer_id: str | None = None
    reason: str | None = None


class SourceVersionListResponse(BaseModel):
    versions: list[SourceVersionRecord]
    total: int
    warnings: list[str] = Field(default_factory=list)


class RegistryReadyPreviewResponse(BaseModel):
    sources: list[RegistryReadySource]
    total: int
    warnings: list[str] = Field(default_factory=list)


class SourceIngestionDryRunRequest(BaseModel):
    target_registry_file: str | None = "data/sources/official_sources.jsonl"


class SourceIngestionDryRunResponse(BaseModel):
    dry_run: bool
    registry_modified: bool
    total_records: int
    valid_records: int
    invalid_records: int
    issues: list[SourceIngestionValidationIssue] = Field(default_factory=list)
    records: list[SourceIngestionRecord] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    target_registry_file: str | None = None


class SourcePublishingPreviewRequest(BaseModel):
    requests: list[SourcePublishRequest] = Field(default_factory=list)
    include_approved_versions: bool = True
