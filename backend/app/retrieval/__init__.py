from typing import Any

from backend.app.retrieval.models import (
    DocumentChunk,
    RetrievalQuery,
    RetrievalResult,
    RetrieverProtocol,
)

__all__ = [
    "DocumentChunk",
    "LocalKeywordRetriever",
    "RetrievalQuery",
    "RetrievalResult",
    "RetrievalService",
    "RetrieverProtocol",
    "apply_ranks",
    "chunk_source",
    "filter_chunks",
    "filter_sources",
    "sort_retrieval_results",
]


def __getattr__(name: str) -> Any:
    if name == "LocalKeywordRetriever":
        from backend.app.retrieval.keyword import LocalKeywordRetriever

        return LocalKeywordRetriever
    if name == "RetrievalService":
        from backend.app.retrieval.service import RetrievalService

        return RetrievalService
    if name == "chunk_source":
        from backend.app.retrieval.chunking import chunk_source

        return chunk_source
    if name in {"filter_chunks", "filter_sources"}:
        from backend.app.retrieval.filters import filter_chunks, filter_sources

        return {"filter_chunks": filter_chunks, "filter_sources": filter_sources}[name]
    if name in {"apply_ranks", "sort_retrieval_results"}:
        from backend.app.retrieval.ranking import apply_ranks, sort_retrieval_results

        return {"apply_ranks": apply_ranks, "sort_retrieval_results": sort_retrieval_results}[
            name
        ]
    raise AttributeError(f"module 'backend.app.retrieval' has no attribute {name!r}")
