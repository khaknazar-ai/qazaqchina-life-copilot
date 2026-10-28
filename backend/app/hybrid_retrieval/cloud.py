"""BM25 + persisted dense vectors + optional rerank over reviewed evidence."""

import json
from hashlib import sha256
from pathlib import Path

import httpx

from backend.app.cloud_ai.budget import CloudRequestBudget
from backend.app.domain.sources import SourceReference
from backend.app.embeddings.cloud_http import RetrievalProviderError
from backend.app.embeddings.models import (
    EmbeddingProviderConfig,
    EmbeddingRequest,
    EmbeddingResponse,
)
from backend.app.embeddings.qwen import QwenEmbeddingProvider
from backend.app.embeddings.safety import eligible_cloud_source, safe_external_text
from backend.app.hybrid_retrieval.models import (
    HybridRetrievalCandidate,
    HybridRetrievalDiagnostics,
    HybridRetrievalRequest,
    HybridRetrievalResult,
)
from backend.app.rag.scoring import source_type_rank
from backend.app.reranking.models import RerankingProviderConfig
from backend.app.reranking.qwen import QwenRerankingProvider
from backend.app.retrieval.bm25 import BM25Index
from backend.app.source_conflicts.registry import full_registry_sources
from backend.app.source_index.models import SourceChunk, SourceIndexBuildRequest
from backend.app.source_index.service import SourceIndexService
from backend.app.source_registry.registry import SourceRegistry
from backend.app.vector_index.persistent import (
    PersistentVectorCache,
    VectorCacheError,
    index_namespace,
)
from backend.app.vector_index.similarity import cosine_similarity

MAX_CORPUS_CHUNKS = 2000
MAX_NEW_DOCUMENT_CHUNKS = 20


class CloudHybridRetrievalService:
    strict_source_eligibility = True

    def __init__(
        self,
        *,
        source_registry: SourceRegistry,
        embedding_config: EmbeddingProviderConfig,
        index_path: Path,
        budget: CloudRequestBudget,
        reranking_config: RerankingProviderConfig | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.source_registry = source_registry
        self.embedding = QwenEmbeddingProvider(embedding_config, budget=budget, transport=transport)
        self.reranker = (
            QwenRerankingProvider(reranking_config, budget=budget, transport=transport)
            if reranking_config and reranking_config.enabled
            else None
        )
        self.cache = PersistentVectorCache(
            index_path,
            namespace=index_namespace(
                provider=embedding_config.provider,
                model=embedding_config.model,
                dimensions=embedding_config.dimensions,
                base_url=self.embedding.client.base_url,
            ),
            dimensions=embedding_config.dimensions,
        )

    def eligible_sources(
        self,
        *,
        scenario: str | None = None,
        risk_level: str | None = None,
        domain: str | None = None,
        city: str | None = None,
        enforce_city_scope: bool = False,
    ) -> list[SourceReference]:
        sources = full_registry_sources(self.source_registry)
        if len({source.source_id for source in sources}) != len(sources):
            return []
        return [
            source
            for source in sources
            if eligible_cloud_source(
                source,
                scenario=scenario,
                risk_level=risk_level,
                domain=domain,
                city=city,
                enforce_city_scope=enforce_city_scope,
            )
        ]

    def eligible_source_registry(
        self,
        *,
        scenario: str | None = None,
        risk_level: str | None = None,
        domain: str | None = None,
        city: str | None = None,
        enforce_city_scope: bool = False,
    ) -> SourceRegistry:
        sources = self.eligible_sources(
            scenario=scenario,
            risk_level=risk_level,
            domain=domain,
            city=city,
            enforce_city_scope=enforce_city_scope,
        )
        ids = {source.source_id for source in sources}
        return SourceRegistry(
            [source for source in sources if source.source_type.value == "official"],
            [source for source in sources if source.source_type.value == "curated_guide"],
            [
                post
                for post in self.source_registry.retrievable_community_posts()
                if post.post_id in ids
            ],
        )

    def retrieve(self, request: HybridRetrievalRequest) -> HybridRetrievalResult:
        diagnostics = HybridRetrievalDiagnostics(
            embedding_provider=self.embedding.config.provider,
            embedding_model=self.embedding.config.model,
            embedding_dimensions=self.embedding.config.dimensions,
        )
        start_calls = self._total_calls()
        try:
            query = safe_external_text(request.query, max_chars=1500)
        except RetrievalProviderError as exc:
            diagnostics.warnings.append(exc.code)
            return HybridRetrievalResult(request=request, candidates=[], diagnostics=diagnostics)
        if request.top_k > 32:
            diagnostics.warnings.append("retrieval_result_limit_exceeded")
            return HybridRetrievalResult(request=request, candidates=[], diagnostics=diagnostics)
        all_sources = full_registry_sources(self.source_registry)
        if len({source.source_id for source in all_sources}) != len(all_sources):
            diagnostics.warnings.append("retrieval_duplicate_source_identity")
            return HybridRetrievalResult(request=request, candidates=[], diagnostics=diagnostics)
        sources = self.eligible_sources(
            scenario=request.scenario,
            risk_level=request.risk_level,
            domain=request.domain,
            city=request.city,
            enforce_city_scope=True,
        )
        diagnostics.unreviewed_excluded_count = len(all_sources) - len(sources)
        cache_sources = self.eligible_sources()
        indexed = SourceIndexService().build_index_from_sources(
            cache_sources,
            SourceIndexBuildRequest(max_chunk_chars=900, overlap_chars=120),
        )
        cache_chunks = [chunk for chunk in indexed.chunks if chunk.indexable and chunk.retrievable]
        if len(cache_chunks) > MAX_CORPUS_CHUNKS:
            diagnostics.warnings.append("retrieval_corpus_limit_exceeded")
            return HybridRetrievalResult(request=request, candidates=[], diagnostics=diagnostics)
        by_id = {source.source_id: source for source in sources}
        chunks = [chunk for chunk in cache_chunks if chunk.source_id in by_id]
        by_chunk = {chunk.chunk_id: chunk for chunk in chunks}
        fingerprints = {source.source_id: _source_fingerprint(source) for source in cache_sources}
        lexical = self._lexical(query, chunks, by_id) if request.include_lexical else []
        diagnostics.lexical_result_count = len(lexical)
        vector: list[HybridRetrievalCandidate] = []
        digest: str | None = None
        try:
            # Revoked or changed sources are removed even when no current query
            # needs vectors. A failed provider call cannot resurrect old rows.
            digest = self.cache.prepare(cache_chunks, fingerprints)
            if request.include_vector and chunks:
                vector = self._vectors(query, chunks, by_id, fingerprints, digest, diagnostics)
        except (RetrievalProviderError, VectorCacheError) as exc:
            code = exc.code if isinstance(exc, RetrievalProviderError) else str(exc)
            diagnostics.warnings.append(code)
            diagnostics.degraded_to_lexical = True
        diagnostics.vector_result_count = len(vector)
        candidates = _fuse_chunks(lexical, vector)
        # Shortlist within every trust pool before sending anything to a model.
        # Four levels of experience can never displace official/curated authority.
        candidates = sorted(candidates, key=_rank_key)[:32]
        if self.reranker and candidates:
            try:
                self._check_sources(fingerprints)
                if digest is not None:
                    self.cache.check_current(digest)
                scores = self.reranker.rerank(
                    query, [by_chunk[c.chunk_id].text for c in candidates]
                )
                candidates = [
                    candidate.model_copy(update={"rerank_score": scores.scores[index]})
                    for index, candidate in enumerate(candidates)
                ]
                diagnostics.reranking_model = scores.model
            except (RetrievalProviderError, VectorCacheError) as exc:
                diagnostics.warnings.append(
                    exc.code if isinstance(exc, RetrievalProviderError) else str(exc),
                )
        if digest is not None:
            try:
                self.cache.check_current(digest)
            except VectorCacheError as exc:
                diagnostics.warnings.append(str(exc))
                # Concurrent corpus updates invalidate dense and rerank results.
                # The caller can retry against the newly built registry snapshot.
                candidates = []
        current = {
            source.source_id: _source_fingerprint(source) for source in self.eligible_sources()
        }
        if current != fingerprints:
            diagnostics.warnings.append("retrieval_source_snapshot_changed")
            candidates = []
        diagnostics.provider_calls = self._total_calls() - start_calls
        diagnostics.used_network = diagnostics.provider_calls > 0
        diagnostics.used_external_provider = diagnostics.used_network
        candidates = sorted(candidates, key=_rank_key)[: request.top_k]
        candidates = [
            candidate.model_copy(update={"final_rank": rank})
            for rank, candidate in enumerate(candidates, start=1)
        ]
        diagnostics.fused_result_count = len(candidates)
        diagnostics.official_count = sum(c.source_type == "official" for c in candidates)
        diagnostics.curated_count = sum(c.source_type == "curated_guide" for c in candidates)
        diagnostics.community_count = (
            len(candidates) - diagnostics.official_count - diagnostics.curated_count
        )
        return HybridRetrievalResult(
            request=request, candidates=candidates, diagnostics=diagnostics
        )

    def _total_calls(self) -> int:
        return self.embedding.client.total_attempts + (
            self.reranker.client.total_attempts if self.reranker else 0
        )

    def _lexical(
        self,
        query: str,
        chunks: list[SourceChunk],
        sources: dict[str, SourceReference],
    ) -> list[HybridRetrievalCandidate]:
        scored = BM25Index([chunk.text for chunk in chunks]).scores(query)
        ranked = sorted(
            [(chunk, score) for chunk, score in zip(chunks, scored, strict=True) if score > 0],
            key=lambda item: (-item[1], item[0].chunk_id),
        )
        return [
            _candidate(chunk, sources[chunk.source_id]).model_copy(
                update={"lexical_rank": rank, "lexical_score": score},
            )
            for rank, (chunk, score) in enumerate(ranked, start=1)
        ]

    def _vectors(
        self,
        query: str,
        chunks: list[SourceChunk],
        sources: dict[str, SourceReference],
        fingerprints: dict[str, str],
        digest: str,
        diagnostics: HybridRetrievalDiagnostics,
    ) -> list[HybridRetrievalCandidate]:
        vectors = self.cache.read(chunks, fingerprints, digest)
        diagnostics.cached_document_count = len(vectors)
        missing = [chunk for chunk in chunks if chunk.chunk_id not in vectors]
        for start in range(0, min(len(missing), MAX_NEW_DOCUMENT_CHUNKS), 10):
            batch = missing[start : start + 10]
            self._check_sources(fingerprints)
            self.cache.check_current(digest)
            response = self._embed([chunk.text for chunk in batch])
            self.cache.put(batch, response.vectors, fingerprints, digest)
            vectors.update(
                {
                    chunk.chunk_id: vector
                    for chunk, vector in zip(batch, response.vectors, strict=True)
                }
            )
            diagnostics.embedded_document_count += len(batch)
        if len(missing) > MAX_NEW_DOCUMENT_CHUNKS:
            raise RetrievalProviderError("retrieval_index_warming")
        self._check_sources(fingerprints)
        self.cache.check_current(digest)
        query_vector = self._embed([query]).vectors[0]
        ranked = sorted(
            [(chunk, cosine_similarity(query_vector, vectors[chunk.chunk_id])) for chunk in chunks],
            key=lambda item: (-item[1], item[0].chunk_id),
        )
        return [
            _candidate(chunk, sources[chunk.source_id]).model_copy(
                update={"vector_rank": rank, "vector_score": score},
            )
            for rank, (chunk, score) in enumerate(ranked, start=1)
            if score > 0
        ]

    def _embed(self, texts: list[str]) -> EmbeddingResponse:
        config = self.embedding.config
        return self.embedding.embed_texts(
            EmbeddingRequest(
                texts=texts,
                provider=config.provider,
                model=config.model,
                dimensions=config.dimensions,
            )
        )

    def _check_sources(self, fingerprints: dict[str, str]) -> None:
        current = {
            source.source_id: _source_fingerprint(source) for source in self.eligible_sources()
        }
        if current != fingerprints:
            raise RetrievalProviderError("retrieval_source_snapshot_changed")


def _candidate(chunk: SourceChunk, source: SourceReference) -> HybridRetrievalCandidate:
    return HybridRetrievalCandidate(
        candidate_id=chunk.chunk_id,
        source_id=chunk.source_id,
        chunk_id=chunk.chunk_id,
        title=source.title,
        text_preview=chunk.text,
        source_type=source.source_type.value,
        trust_level=source.trust_level.value,
        freshness_status=chunk.freshness_status,
        retrievable=True,
        indexable=True,
    )


def _source_fingerprint(source: SourceReference) -> str:
    return sha256(json.dumps(source.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()


def _rank_key(candidate: HybridRetrievalCandidate) -> tuple:
    return (
        source_type_rank(candidate.source_type, candidate.trust_level),
        -(candidate.rerank_score if candidate.rerank_score is not None else candidate.fused_score),
        -candidate.fused_score,
        candidate.candidate_id,
    )


def _fuse_chunks(
    lexical: list[HybridRetrievalCandidate],
    vector: list[HybridRetrievalCandidate],
) -> list[HybridRetrievalCandidate]:
    merged: dict[str, HybridRetrievalCandidate] = {}
    for candidate in [*lexical, *vector]:
        key = candidate.chunk_id or candidate.candidate_id
        previous = merged.get(key)
        if previous:
            candidate = previous.model_copy(
                update={
                    "vector_rank": candidate.vector_rank,
                    "vector_score": candidate.vector_score,
                }
            )
        merged[key] = candidate
    return [
        candidate.model_copy(
            update={
                "fused_score": sum(
                    1 / (60 + rank)
                    for rank in (candidate.lexical_rank, candidate.vector_rank)
                    if rank
                )
            }
        )
        for candidate in merged.values()
    ]
