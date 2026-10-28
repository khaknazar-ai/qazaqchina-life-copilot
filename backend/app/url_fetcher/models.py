from pydantic import BaseModel, Field

from backend.app.source_candidates.models import SourceCandidate


class URLSafetyCheck(BaseModel):
    url: str
    allowed: bool
    normalized_url: str | None = None
    reason: str | None = None
    warnings: list[str] = Field(default_factory=list)


class URLFetchRequest(BaseModel):
    url: str
    allow_network: bool = False
    timeout_seconds: float = Field(default=8.0, gt=0)
    max_bytes: int = Field(default=200_000, gt=0)
    max_redirects: int = Field(default=2, ge=0)
    scenario: str | None = None
    risk_level: str | None = None
    language: str | None = None
    city: str | None = None


class URLFetchResult(BaseModel):
    url: str
    final_url: str | None = None
    fetched: bool = False
    used_network: bool = False
    status_code: int | None = None
    content_type: str | None = None
    title: str | None = None
    text_preview: str | None = None
    content_hash: str | None = None
    bytes_read: int = 0
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None


class URLToCandidateResult(BaseModel):
    fetch_result: URLFetchResult
    candidate: SourceCandidate | None = None
    warnings: list[str] = Field(default_factory=list)
