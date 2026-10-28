from pydantic import BaseModel, Field


class HybridRAGRequest(BaseModel):
    user_message: str
    city: str | None = Field(default=None, max_length=100)
    scenario: str | None = None
    risk_level: str | None = None
    language: str | None = None
    max_queries: int = Field(default=6, gt=0)
    max_results_per_query: int = Field(default=6, gt=0)
    max_evidence: int = Field(default=5, gt=0)
    include_answer_draft: bool = True
    use_semantic_retrieval: bool = False
    semantic_top_k: int = Field(default=5, gt=0)


class HybridQueryRun(BaseModel):
    query: str
    reason: str | None = None
    weight: float = 1.0
    retrieved_count: int = 0
    source_ids: list[str] = Field(default_factory=list)


class HybridEvidenceItem(BaseModel):
    source_id: str
    chunk_id: str | None = None
    version_id: str | None = None
    title: str
    excerpt: str
    source_type: str | None = None
    trust_level: str | None = None
    rank: int
    score: float
    fused_score: float
    lexical_score: float | None = None
    vector_score: float | None = None
    rerank_score: float | None = None
    retrieval_rank: int | None = None
    used_for: str = "grounding"
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    freshness_status: str | None = None
    source_version_status: str | None = None


class HybridRAGCoverage(BaseModel):
    trusted_evidence_count: int
    official_count: int
    curated_count: int
    community_count: int
    has_official_or_curated: bool
    has_policy_required_source: bool
    warnings: list[str] = Field(default_factory=list)
    freshness_warnings: list[str] = Field(default_factory=list)
    fresh_count: int = 0
    stale_count: int = 0
    unknown_count: int = 0
    needs_refresh_count: int = 0


class HybridRAGResult(BaseModel):
    request: HybridRAGRequest
    domain: str
    query_runs: list[HybridQueryRun]
    evidence: list[HybridEvidenceItem]
    coverage: HybridRAGCoverage
    quality_report: dict | None = None
    answer_draft: dict | None = None
    used_network: bool = False
    used_provider_call: bool = False
    warnings: list[str] = Field(default_factory=list)
    freshness_warnings: list[str] = Field(default_factory=list)
    semantic_retrieval_enabled: bool = False
    semantic_retrieval_diagnostics: dict = Field(default_factory=dict)
