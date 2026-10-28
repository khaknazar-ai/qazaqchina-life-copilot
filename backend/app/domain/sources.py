from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, Field

from backend.app.domain.enums import (
    LanguageCode,
    ModerationStatus,
    RiskLevel,
    SourceType,
    TrustLevel,
    UserScenario,
)


class SourceReference(BaseModel):
    source_id: str
    title: str
    source_type: SourceType
    trust_level: TrustLevel
    content: str | None = None
    reviewed_answer_passages: list[Annotated[str, Field(min_length=12, max_length=2400)]] = Field(
        default_factory=list,
        max_length=12,
    )
    reviewed_answer_passages_complete: bool = False
    language: LanguageCode = LanguageCode.unknown
    url: str | None = None
    date_published: date | None = None
    date_accessed: date | None = None
    collected_at: datetime | None = None
    reviewed_at: datetime | None = None
    last_reviewed_at: datetime | None = None
    expires_at: datetime | None = None
    content_hash: str | None = None
    freshness_note: str | None = None
    status_override: str | None = None
    based_on_source_ids: list[str] = Field(default_factory=list)
    reviewed_by: str | None = None
    city: str | None = None
    scenario: UserScenario | None = None
    risk_tags: list[RiskLevel] = Field(default_factory=list)
    moderation_status: ModerationStatus | None = None
    allow_ai_retrieval: bool = True


class Citation(BaseModel):
    citation_id: str
    source_id: str
    claim: str
    supporting_quote: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class RetrievedSource(BaseModel):
    source: SourceReference
    chunk_id: str
    content: str
    score: float | None = None
    rank: int | None = None


class SourceConflict(BaseModel):
    conflict_id: str
    higher_trust_source_id: str
    lower_trust_source_id: str
    summary: str
    resolution: str


_TRUST_LEVEL_RANKS: dict[TrustLevel, int] = {
    TrustLevel.level_1_official: 1,
    TrustLevel.level_2_curated: 2,
    TrustLevel.level_3_verified_institutional: 3,
    TrustLevel.level_4_verified_experienced: 4,
    TrustLevel.level_5_ordinary_community: 5,
    TrustLevel.level_6_untrusted: 6,
}

_COMMUNITY_SOURCE_TYPES = {
    SourceType.verified_institutional_contributor,
    SourceType.verified_experienced_contributor,
    SourceType.ordinary_community,
}


def trust_level_rank(trust_level: TrustLevel) -> int:
    return _TRUST_LEVEL_RANKS[trust_level]


def is_retrievable_source(source: SourceReference) -> bool:
    if not source.allow_ai_retrieval:
        return False
    if not retrieval_status_allowed(source.moderation_status, source.status_override):
        return False

    if (
        source.trust_level == TrustLevel.level_6_untrusted
        or source.source_type == SourceType.untrusted
    ):
        return False

    if source.source_type in _COMMUNITY_SOURCE_TYPES:
        return source.moderation_status == ModerationStatus.approved

    return source.source_type in {SourceType.official, SourceType.curated_guide}


def retrieval_status_allowed(moderation: str | None, status: str | None = None) -> bool:
    """Every trust tier obeys moderation and revocation; unknown states fail closed."""
    return (moderation or "").casefold() in {"", "approved"} and (status or "").casefold() in {
        "",
        "active",
        "approved",
        "published",
        "current",
    }


def source_outranks(source_a: SourceReference, source_b: SourceReference) -> bool:
    return trust_level_rank(source_a.trust_level) < trust_level_rank(source_b.trust_level)


def official_sources_outrank(source_a: SourceReference, source_b: SourceReference) -> bool:
    return source_outranks(source_a, source_b)
