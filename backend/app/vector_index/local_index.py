from backend.app.embeddings.models import EmbeddingRecord
from backend.app.vector_index.models import (
    VectorIndexManifest,
    VectorSearchFilter,
    VectorSearchRequest,
    VectorSearchResult,
)
from backend.app.vector_index.similarity import cosine_similarity


class LocalVectorIndex:
    def __init__(self, records: list[EmbeddingRecord] | None = None) -> None:
        self._records: list[EmbeddingRecord] = []
        if records:
            self.add_records(records)

    def add_record(self, record: EmbeddingRecord) -> None:
        self._records.append(record)

    def add_records(self, records: list[EmbeddingRecord]) -> None:
        for record in records:
            self.add_record(record)

    def build_manifest(self) -> VectorIndexManifest:
        indexed_records = [record for record in self._records if _record_is_indexed(record)]
        dimensions = _single_or_none([record.dimensions for record in indexed_records])
        provider = _single_or_none([record.provider for record in indexed_records])
        model = _single_or_none([record.model for record in indexed_records])
        warnings = _manifest_warnings(self._records, indexed_records, dimensions, provider, model)
        return VectorIndexManifest(
            total_records=len(self._records),
            indexed_records=len(indexed_records),
            skipped_records=len(self._records) - len(indexed_records),
            dimensions=dimensions,
            provider=provider,
            model=model,
            used_network=False,
            used_external_provider=False,
            warnings=warnings,
        )

    def search(self, request: VectorSearchRequest) -> list[VectorSearchResult]:
        candidates = [
            record for record in self._records if _record_matches_filter(record, request.filters)
        ]
        scored: list[tuple[float, EmbeddingRecord]] = []
        for record in candidates:
            try:
                score = cosine_similarity(request.query_vector, record.vector)
            except ValueError:
                score = 0.0
            scored.append((score, record))
        ranked = sorted(scored, key=lambda item: (-item[0], item[1].embedding_id))[
            : request.top_k
        ]
        return [
            _search_result(record=record, score=score, rank=rank)
            for rank, (score, record) in enumerate(ranked, start=1)
        ]


def _record_is_indexed(record: EmbeddingRecord) -> bool:
    return record.indexable and record.retrievable


def _record_matches_filter(
    record: EmbeddingRecord,
    filters: VectorSearchFilter,
) -> bool:
    if filters.require_indexable and not record.indexable:
        return False
    if filters.require_retrievable and not record.retrievable:
        return False
    for field_name in [
        "source_type",
        "trust_level",
        "freshness_status",
        "source_version_status",
    ]:
        expected = getattr(filters, field_name)
        if expected is not None and getattr(record, field_name) != expected:
            return False
    return True


def _search_result(record: EmbeddingRecord, score: float, rank: int) -> VectorSearchResult:
    metadata = {
        "indexable": record.indexable,
        "retrievable": record.retrievable,
        "dimensions": record.dimensions,
        "text_hash": record.text_hash,
    }
    return VectorSearchResult(
        rank=rank,
        score=score,
        embedding_id=record.embedding_id,
        chunk_id=record.chunk_id,
        source_id=record.source_id,
        version_id=record.version_id,
        provider=record.provider,
        model=record.model,
        source_type=record.source_type,
        trust_level=record.trust_level,
        freshness_status=record.freshness_status,
        source_version_status=record.source_version_status,
        metadata=metadata,
        warnings=list(record.warnings),
    )


def _single_or_none(values: list[object]) -> object | None:
    unique_values = list(dict.fromkeys(values))
    if len(unique_values) == 1:
        return unique_values[0]
    return None


def _manifest_warnings(
    records: list[EmbeddingRecord],
    indexed_records: list[EmbeddingRecord],
    dimensions: object | None,
    provider: object | None,
    model: object | None,
) -> list[str]:
    warnings: list[str] = []
    skipped = len(records) - len(indexed_records)
    if skipped:
        warnings.append("Non-indexable or non-retrievable embedding records were skipped.")
    if records and dimensions is None:
        warnings.append("Embedding records have mixed dimensions.")
    if indexed_records and provider is None:
        warnings.append("Embedding records have mixed providers.")
    if indexed_records and model is None:
        warnings.append("Embedding records have mixed models.")
    warnings.extend(warning for record in indexed_records for warning in record.warnings)
    return list(dict.fromkeys(warnings))
