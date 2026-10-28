from backend.app.rag.models import HybridEvidenceItem
from backend.app.rag.scoring import source_type_rank


def reciprocal_rank_fusion(
    ranked_lists: list[list[HybridEvidenceItem]],
    k: int = 60,
) -> list[HybridEvidenceItem]:
    merged: dict[str, HybridEvidenceItem] = {}
    fused_scores: dict[str, float] = {}

    for ranked_list in ranked_lists:
        for index, item in enumerate(ranked_list, start=1):
            rank = item.rank or index
            fused_scores[item.source_id] = (
                fused_scores.get(item.source_id, 0.0) + 1.0 / (k + rank)
            )
            existing = merged.get(item.source_id)
            if existing is None:
                merged[item.source_id] = item
                continue
            merged[item.source_id] = _merge_evidence_items(existing, item)

    fused_items = [
        item.model_copy(update={"fused_score": fused_scores.get(item.source_id, 0.0)})
        for item in merged.values()
    ]
    return _assign_ranks(sort_evidence_items(fused_items))


def dedupe_evidence_items(items: list[HybridEvidenceItem]) -> list[HybridEvidenceItem]:
    deduped: dict[str, HybridEvidenceItem] = {}
    for item in items:
        existing = deduped.get(item.source_id)
        if existing is None:
            deduped[item.source_id] = item
            continue
        deduped[item.source_id] = _merge_evidence_items(existing, item)
    return _assign_ranks(sort_evidence_items(list(deduped.values())))


def sort_evidence_items(items: list[HybridEvidenceItem]) -> list[HybridEvidenceItem]:
    return sorted(
        items,
        key=lambda item: (
            -item.fused_score,
            -item.score,
            source_type_rank(item.source_type, item.trust_level),
            item.source_id,
        ),
    )


def _merge_evidence_items(
    existing: HybridEvidenceItem,
    incoming: HybridEvidenceItem,
) -> HybridEvidenceItem:
    best = incoming if incoming.score > existing.score else existing
    return best.model_copy(
        update={
            "score": max(existing.score, incoming.score),
            "fused_score": max(existing.fused_score, incoming.fused_score),
            "rank": min(existing.rank, incoming.rank),
            "reasons": _merge_strings(existing.reasons, incoming.reasons),
            "warnings": _merge_strings(existing.warnings, incoming.warnings),
            "excerpt": best.excerpt or existing.excerpt or incoming.excerpt,
        }
    )


def _assign_ranks(items: list[HybridEvidenceItem]) -> list[HybridEvidenceItem]:
    return [item.model_copy(update={"rank": rank}) for rank, item in enumerate(items, start=1)]


def _merge_strings(first: list[str], second: list[str]) -> list[str]:
    return list(dict.fromkeys([*first, *second]))
