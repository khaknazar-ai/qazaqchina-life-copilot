from pydantic import BaseModel, Field


class SourceChunk(BaseModel):
    chunk_id: str
    source_id: str
    version_id: str | None = None
    chunk_index: int
    text: str
    text_hash: str
    source_type: str | None = None
    trust_level: str | None = None
    language: str | None = None
    country: str | None = None
    city: str | None = None
    content_hash: str | None = None
    freshness_status: str | None = None
    source_version_status: str | None = None
    retrievable: bool = True
    indexable: bool = True
    warnings: list[str] = Field(default_factory=list)


class SourceIndexBuildRequest(BaseModel):
    max_chunk_chars: int = 900
    overlap_chars: int = 120
    include_non_retrievable: bool = False
    include_deprecated: bool = False


class SourceIndexBuildResult(BaseModel):
    total_sources: int
    total_chunks: int
    indexable_chunks: int
    non_indexable_chunks: int
    chunks: list[SourceChunk]
    warnings: list[str] = Field(default_factory=list)
