from datetime import datetime

from pydantic import BaseModel, Field

from backend.app.domain.enums import (
    LanguageCode,
    ModerationStatus,
    UserScenario,
    VerificationStatus,
    VerifiedContributorRole,
)


class ContributorProfile(BaseModel):
    contributor_id: str
    display_name: str
    self_declared_role: str | None = None
    verified_role: VerifiedContributorRole = VerifiedContributorRole.ordinary_user
    verification_status: VerificationStatus = VerificationStatus.unverified
    institution_name: str | None = None
    verified_at: datetime | None = None
    verification_expires_at: datetime | None = None

    @property
    def active_verified_role(self) -> VerifiedContributorRole:
        if self.verification_status == VerificationStatus.verified:
            return self.verified_role
        return VerifiedContributorRole.ordinary_user


class CommunityPost(BaseModel):
    post_id: str
    author: ContributorProfile
    title: str
    city: str | None = None
    scenario: UserScenario
    language: LanguageCode
    situation: str
    what_happened: str
    what_helped: str | None = None
    required_documents: list[str] = Field(default_factory=list)
    mistakes_to_avoid: list[str] = Field(default_factory=list)
    advice_for_others: str | None = None
    tags: list[str] = Field(default_factory=list)
    moderation_status: ModerationStatus = ModerationStatus.pending
    allow_ai_retrieval: bool = False
    # None preserves reviewed legacy records; newly submitted posts record explicit consent.
    ai_retrieval_consent: bool | None = None
    created_at: datetime

    @property
    def can_be_used_by_ai(self) -> bool:
        return (
            self.moderation_status == ModerationStatus.approved
            and self.allow_ai_retrieval
            and self.ai_retrieval_consent is not False
        )
