from backend.app.hybrid_retrieval.models import HybridRetrievalCandidate

_SOURCE_TYPE_PRIORITY = {
    "official": 1,
    "curated_guide": 2,
    "verified_institutional_contributor": 3,
    "verified_experienced_contributor": 4,
    "ordinary_community": 5,
}
_TRUST_LEVEL_PRIORITY = {
    "level_1_official": 1,
    "level_2_curated": 2,
    "level_3_verified_institutional": 3,
    "level_4_verified_experienced": 4,
    "level_5_ordinary_community": 5,
}


def reciprocal_rank(rank: int | None, k: int = 60) -> float:
    if rank is None or rank <= 0:
        return 0.0
    return 1.0 / (k + rank)


def merge_lexical_and_vector_candidates(
    lexical: list[HybridRetrievalCandidate],
    vector: list[HybridRetrievalCandidate],
) -> list[HybridRetrievalCandidate]:
    merged: dict[str, HybridRetrievalCandidate] = {}
    for candidate in [*lexical, *vector]:
        candidate_key = _candidate_identity(candidate)
        normalized = candidate.model_copy(update={"candidate_id": candidate_key})
        existing = merged.get(candidate_key)
        if existing is None:
            merged[candidate_key] = normalized
            continue
        merged[candidate_key] = _merge_candidate(existing, normalized, candidate_key)
    return list(merged.values())


def fuse_candidates(
    candidates: list[HybridRetrievalCandidate],
    top_k: int = 5,
) -> list[HybridRetrievalCandidate]:
    fused = [
        candidate.model_copy(
            update={
                "candidate_id": _candidate_identity(candidate),
                "fused_score": reciprocal_rank(candidate.lexical_rank)
                + reciprocal_rank(candidate.vector_rank),
            }
        )
        for candidate in candidates
    ]
    ranked = sorted(
        fused,
        key=lambda candidate: (
            _source_priority(candidate),
            -candidate.fused_score,
            candidate.candidate_id,
        ),
    )[:top_k]
    return [
        candidate.model_copy(update={"final_rank": rank})
        for rank, candidate in enumerate(ranked, start=1)
    ]


def _merge_candidate(
    existing: HybridRetrievalCandidate,
    incoming: HybridRetrievalCandidate,
    candidate_key: str,
) -> HybridRetrievalCandidate:
    return existing.model_copy(
        update={
            "candidate_id": candidate_key,
            "chunk_id": existing.chunk_id or incoming.chunk_id,
            "version_id": existing.version_id or incoming.version_id,
            "title": existing.title or incoming.title,
            "text_preview": existing.text_preview or incoming.text_preview,
            "source_type": existing.source_type or incoming.source_type,
            "trust_level": existing.trust_level or incoming.trust_level,
            "freshness_status": existing.freshness_status or incoming.freshness_status,
            "source_version_status": (
                existing.source_version_status or incoming.source_version_status
            ),
            "lexical_rank": _best_rank(existing.lexical_rank, incoming.lexical_rank),
            "lexical_score": _best_score(existing.lexical_score, incoming.lexical_score),
            "vector_rank": _best_rank(existing.vector_rank, incoming.vector_rank),
            "vector_score": _best_score(existing.vector_score, incoming.vector_score),
            "retrievable": existing.retrievable and incoming.retrievable,
            "indexable": existing.indexable and incoming.indexable,
            "warnings": _unique([*existing.warnings, *incoming.warnings]),
        }
    )


def _candidate_identity(candidate: HybridRetrievalCandidate) -> str:
    if candidate.version_id:
        return f"{candidate.source_id}::{candidate.version_id}"
    return candidate.source_id


def _source_priority(candidate: HybridRetrievalCandidate) -> int:
    source_type = _normalize(candidate.source_type)
    trust_level = _normalize(candidate.trust_level)
    if source_type in _SOURCE_TYPE_PRIORITY:
        return _SOURCE_TYPE_PRIORITY[source_type]
    if trust_level in _TRUST_LEVEL_PRIORITY:
        return _TRUST_LEVEL_PRIORITY[trust_level]
    return 6


def _best_rank(first: int | None, second: int | None) -> int | None:
    ranks = [rank for rank in [first, second] if rank is not None]
    return min(ranks) if ranks else None


def _best_score(first: float | None, second: float | None) -> float | None:
    scores = [score for score in [first, second] if score is not None]
    return max(scores) if scores else None


def _normalize(value: str | None) -> str:
    return (value or "").casefold()


def _unique(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        if value not in deduped:
            deduped.append(value)
    return deduped
