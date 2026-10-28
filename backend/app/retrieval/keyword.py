import re

from backend.app.domain.community import CommunityPost
from backend.app.domain.sources import SourceReference, trust_level_rank
from backend.app.retrieval.bm25 import BM25Index
from backend.app.retrieval.chunking import chunk_source
from backend.app.retrieval.filters import filter_chunks, filter_sources
from backend.app.retrieval.models import DocumentChunk, RetrievalQuery, RetrievalResult
from backend.app.retrieval.ranking import apply_ranks, sort_retrieval_results, source_trust_bonus
from backend.app.source_registry.registry import SourceRegistry

TOKEN_PATTERN = re.compile(r"[\w\u0400-\u04ff\u4e00-\u9fff]+", re.UNICODE)


class LocalKeywordRetriever:
    def __init__(
        self, source_registry: SourceRegistry, *, algorithm: str = "keyword",
        trusted_fallback: bool = True,
    ) -> None:
        if algorithm not in {"keyword", "bm25"}:
            raise ValueError("Unknown lexical retrieval algorithm.")
        self.source_registry = source_registry
        self.algorithm = algorithm
        self.trusted_fallback = trusted_fallback

    def retrieve(self, query: RetrievalQuery) -> list[RetrievalResult]:
        chunks = filter_chunks(self._build_chunks(query.include_community), query)
        if self.algorithm == "bm25":
            scores = BM25Index([_searchable_text(chunk) for chunk in chunks]).scores(query.query)
            results = [
                RetrievalResult(chunk=chunk, score=score, match_reasons=["bm25_match"])
                for chunk, score in zip(chunks, scores, strict=True) if score > 0
            ]
            if not results and self.trusted_fallback:
                results = self._fallback_results(query)
            return apply_ranks(sort_retrieval_results(results)[: query.max_results])
        query_tokens = _tokenize(query.query)
        scored_results = [
            result
            for chunk in chunks
            if (result := self._score_chunk(chunk, query, query_tokens)).score > 0
        ]

        if not scored_results and self.trusted_fallback:
            scored_results = self._fallback_results(query)

        sorted_results = sort_retrieval_results(scored_results)
        return apply_ranks(sorted_results[: query.max_results])

    def _build_chunks(self, include_community: bool) -> list[DocumentChunk]:
        chunks: list[DocumentChunk] = []

        source_references = [
            *self.source_registry.official_sources(),
            *self.source_registry.curated_guides(),
        ]
        for source in source_references:
            chunks.extend(chunk_source(source, _source_text(source)))

        if include_community:
            for post in self.source_registry.retrievable_community_posts():
                source = self.source_registry.get_source_by_id(post.post_id)
                if source is not None:
                    chunks.extend(chunk_source(source, _community_post_text(post)))

        return chunks

    def _score_chunk(
        self,
        chunk: DocumentChunk,
        query: RetrievalQuery,
        query_tokens: list[str],
    ) -> RetrievalResult:
        searchable_text = _searchable_text(chunk)
        match_count = sum(1 for token in query_tokens if token in searchable_text)
        score = float(match_count)
        match_reasons: list[str] = []

        if match_count:
            match_reasons.append("keyword_match")

        if query.scenario is not None and chunk.source.scenario == query.scenario:
            score += 0.25
            match_reasons.append("scenario_match")

        if (
            query.city is not None
            and chunk.source.city is not None
            and chunk.source.city.casefold() == query.city.casefold()
        ):
            score += 0.15
            match_reasons.append("city_match")

        if score > 0:
            trust_bonus = source_trust_bonus(chunk.source)
            score += trust_bonus
            if trust_bonus > 0:
                match_reasons.append("source_trust_bonus")

        return RetrievalResult(chunk=chunk, score=score, match_reasons=match_reasons)

    def _fallback_results(self, query: RetrievalQuery) -> list[RetrievalResult]:
        filtered_sources = filter_sources(self.source_registry.retrievable_sources(), query)
        sorted_sources = sorted(
            filtered_sources,
            key=lambda source: (trust_level_rank(source.trust_level), source.source_id),
        )
        return [
            RetrievalResult(
                chunk=DocumentChunk(
                    chunk_id=f"{source.source_id}::fallback-0",
                    source=source,
                    content=_source_text(source),
                    metadata={"fallback": "true"},
                ),
                score=0.1,
                match_reasons=["trusted_fallback"],
            )
            for source in sorted_sources[: query.max_results]
        ]


def _source_text(source: SourceReference) -> str:
    parts = [
        source.title,
        source.content or "",
        source.source_id,
        source.source_type.value,
        source.trust_level.value,
        source.language.value,
        source.city or "",
        source.scenario.value if source.scenario else "",
        " ".join(risk_tag.value for risk_tag in source.risk_tags),
    ]
    return "\n".join(part for part in parts if part)


def _community_post_text(post: CommunityPost) -> str:
    parts = [
        post.title,
        post.situation,
        post.what_happened,
        post.what_helped or "",
        post.advice_for_others or "",
    ]
    return "\n".join(part for part in parts if part)


def _searchable_text(chunk: DocumentChunk) -> str:
    metadata_text = " ".join(chunk.metadata.values())
    return f"{chunk.content} {chunk.source.title} {metadata_text}".casefold()


def _tokenize(text: str) -> list[str]:
    return [token.casefold() for token in TOKEN_PATTERN.findall(text) if token.strip()]
