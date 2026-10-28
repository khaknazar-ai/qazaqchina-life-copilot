from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class VectorSearchFilter(BaseModel):
    source_type: str | None = None
    trust_level: str | None = None
    freshness_status: str | None = None
    source_version_status: str | None = None
    require_indexable: bool = True
    require_retrievable: bool = True


class VectorSearchRequest(BaseModel):
    query_vector: list[float]
    top_k: int = Field(default=5, gt=0)
    filters: VectorSearchFilter = Field(default_factory=VectorSearchFilter)


class VectorSearchResult(BaseModel):
    rank: int
    score: float
    embedding_id: str
    chunk_id: str
    source_id: str
    version_id: str | None = None
    provider: str
    model: str
    source_type: str | None = None
    trust_level: str | None = None
    freshness_status: str | None = None
    source_version_status: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class VectorIndexManifest(BaseModel):
    generated_at: datetime = Field(default_factory=utc_now)
    total_records: int
    indexed_records: int
    skipped_records: int
    dimensions: int | None = None
    provider: str | None = None
    model: str | None = None
    used_network: bool = False
    used_external_provider: bool = False
    warnings: list[str] = Field(default_factory=list)

    @field_validator("generated_at")
    @classmethod
    def _generated_at_must_be_utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value)


class VectorIndexInspectionReport(BaseModel):
    manifest: VectorIndexManifest
    sample_results: list[VectorSearchResult] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
