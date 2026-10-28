from pydantic import BaseModel, Field


class HybridRetrievalRequest(BaseModel):
    query: str
    city: str | None = Field(default=None, max_length=100)
    scenario: str | None = None
    risk_level: str | None = None
    domain: str | None = None
    top_k: int = Field(default=5, gt=0)
    include_lexical: bool = True
    include_vector: bool = True
    require_trusted_sources: bool = True
    exclude_deprecated: bool = True
    exclude_unreviewed: bool = True


class HybridRetrievalCandidate(BaseModel):
    candidate_id: str
    source_id: str
    chunk_id: str | None = None
    version_id: str | None = None
    title: str | None = None
    text_preview: str | None = None
    source_type: str | None = None
    trust_level: str | None = None
    freshness_status: str | None = None
    source_version_status: str | None = None
    lexical_rank: int | None = None
    lexical_score: float | None = None
    vector_rank: int | None = None
    vector_score: float | None = None
    fused_score: float = 0.0
    final_rank: int | None = None
    rerank_score: float | None = None
    retrievable: bool = True
    indexable: bool = True
    warnings: list[str] = Field(default_factory=list)


class HybridRetrievalDiagnostics(BaseModel):
    lexical_result_count: int = 0
    vector_result_count: int = 0
    fused_result_count: int = 0
    official_count: int = 0
    curated_count: int = 0
    community_count: int = 0
    stale_count: int = 0
    unknown_freshness_count: int = 0
    deprecated_excluded_count: int = 0
    unreviewed_excluded_count: int = 0
    used_network: bool = False
    used_external_provider: bool = False
    used_external_vector_db: bool = False
    provider_calls: int = 0
    cached_document_count: int = 0
    embedded_document_count: int = 0
    embedding_provider: str | None = None
    embedding_model: str | None = None
    embedding_dimensions: int | None = None
    reranking_model: str | None = None
    degraded_to_lexical: bool = False
    warnings: list[str] = Field(default_factory=list)


class HybridRetrievalResult(BaseModel):
    request: HybridRetrievalRequest
    candidates: list[HybridRetrievalCandidate]
    diagnostics: HybridRetrievalDiagnostics
