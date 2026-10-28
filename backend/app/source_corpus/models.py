"""Review packets describe evidence, not authority inferred from a hostname."""

from datetime import UTC, date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.domain.enums import LanguageCode, RiskLevel, UserScenario


class CorpusPacket(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: str
    source_id: str
    title: str
    publisher: str
    requested_url: str
    final_url: str | None = None
    jurisdiction_or_scope: str
    language: LanguageCode
    topics: list[str] = Field(default_factory=list)
    publication_date: date | None = None
    publication_date_basis: str | None = None
    captured_at: datetime | None = None
    raw_path: str | None = None
    raw_sha256: str | None = None
    raw_bytes: int = 0
    extracted_path: str | None = None
    extracted_sha256: str | None = None
    text: str = ""
    text_sha256: str
    extraction_method: str | None = None
    status: Literal["pending", "blocked"] = "blocked"
    findings: list[str] = Field(default_factory=list)
    rights_status: str | None = None
    requires_review: bool = True
    allow_ai_retrieval: bool = False


class PublicationReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_text_sha256: str
    expected_revision_hash: str
    expires_at: datetime
    scenario: UserScenario | None = None
    city: str | None = None
    risk_tags: list[RiskLevel] = Field(default_factory=list)
    answer_passages: list[Annotated[str, Field(min_length=12, max_length=2400)]] = Field(
        default_factory=list,
        max_length=12,
    )
    answer_passages_complete: bool = False
    publisher_verified: bool
    full_text_verified: bool
    applicability_verified: bool
    dates_verified: bool
    reuse_verified: bool
    note: str = Field(min_length=1, max_length=1000)

    @field_validator("expires_at")
    @classmethod
    def aware_expiry(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Expiry must include a timezone")
        return value.astimezone(UTC)


class CorpusRevision(BaseModel):
    revision_id: str
    revision_hash: str
    packet: CorpusPacket
    staged_at: datetime


class CorpusState(BaseModel):
    revision: CorpusRevision
    status: Literal["pending", "blocked", "approved", "revoked"]
    approvals: list[dict] = Field(default_factory=list)
    event_count: int
