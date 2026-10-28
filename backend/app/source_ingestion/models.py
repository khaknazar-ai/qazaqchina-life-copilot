from datetime import UTC, datetime

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


class SourceIngestionValidationIssue(BaseModel):
    severity: str
    code: str
    message: str
    candidate_id: str | None = None


class SourceIngestionRecord(BaseModel):
    candidate_id: str
    source_id: str
    title: str
    url: str
    source_type: str
    trust_level: str
    language: str | None = None
    country: str | None = "CN"
    city: str | None = None
    excerpt: str
    allow_retrieval: bool
    freshness_note: str | None = None
    warnings: list[str] = Field(default_factory=list)


class SourceIngestionManifest(BaseModel):
    generated_at: datetime = Field(default_factory=utc_now)
    dry_run: bool = True
    total_records: int
    valid_records: int
    invalid_records: int
    records: list[SourceIngestionRecord]
    issues: list[SourceIngestionValidationIssue] = Field(default_factory=list)
    target_registry_file: str | None = None
    notes: list[str] = Field(default_factory=list)


class SourceIngestionResult(BaseModel):
    manifest: SourceIngestionManifest
    output_paths: list[str] = Field(default_factory=list)
    registry_modified: bool = False
