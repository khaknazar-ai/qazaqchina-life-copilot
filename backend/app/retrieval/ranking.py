from backend.app.domain.sources import SourceReference, trust_level_rank
from backend.app.retrieval.models import RetrievalResult


def source_trust_bonus(source: SourceReference) -> float:
    return {
        1: 0.6,
        2: 0.5,
        3: 0.3,
        4: 0.2,
        5: 0.1,
        6: 0.0,
    }[trust_level_rank(source.trust_level)]


def sort_retrieval_results(results: list[RetrievalResult]) -> list[RetrievalResult]:
    return sorted(
        results,
        key=lambda result: (
            -result.score,
            trust_level_rank(result.chunk.source.trust_level),
            result.chunk.source.source_id,
            result.chunk.chunk_index,
        ),
    )


def apply_ranks(results: list[RetrievalResult]) -> list[RetrievalResult]:
    ranked_results: list[RetrievalResult] = []
    for rank, result in enumerate(results, start=1):
        ranked_results.append(result.model_copy(update={"rank": rank}))
    return ranked_results
