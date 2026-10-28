from datetime import UTC, datetime

from pydantic import BaseModel, Field, SecretStr, field_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class EmbeddingProviderConfig(BaseModel):
    provider: str = "fake"
    model: str = "fake-hash-embedding-v1"
    dimensions: int = 16
    enabled: bool = True
    allow_external: bool = False
    base_url: str | None = None
    api_key: SecretStr | None = Field(default=None, exclude=True, repr=False)
    timeout_seconds: float = Field(default=30, ge=1, le=60)
    max_attempts: int = Field(default=2, ge=1, le=2)


class EmbeddingRequest(BaseModel):
    texts: list[str]
    provider: str = "fake"
    model: str = "fake-hash-embedding-v1"
    dimensions: int = 16


class EmbeddingResponse(BaseModel):
    vectors: list[list[float]]
    provider: str
    model: str
    dimensions: int
    used_network: bool = False
    used_external_provider: bool = False
    warnings: list[str] = Field(default_factory=list)
    provider_calls: int = 0


class EmbeddingRecord(BaseModel):
    embedding_id: str
    chunk_id: str
    source_id: str
    version_id: str | None = None
    text_hash: str
    provider: str
    model: str
    dimensions: int
    vector: list[float]
    created_at: datetime = Field(default_factory=utc_now)
    indexable: bool = True
    retrievable: bool = True
    source_type: str | None = None
    trust_level: str | None = None
    freshness_status: str | None = None
    source_version_status: str | None = None
    warnings: list[str] = Field(default_factory=list)

    @field_validator("created_at")
    @classmethod
    def _created_at_must_be_utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value)


class EmbeddingBuildManifest(BaseModel):
    generated_at: datetime = Field(default_factory=utc_now)
    provider: str
    model: str
    dimensions: int
    total_chunks: int
    embedded_chunks: int
    skipped_chunks: int
    used_network: bool = False
    used_external_provider: bool = False
    records: list[EmbeddingRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("generated_at")
    @classmethod
    def _generated_at_must_be_utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value)
