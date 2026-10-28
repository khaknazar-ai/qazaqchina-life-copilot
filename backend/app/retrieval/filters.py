from backend.app.domain.enums import RiskLevel, SourceType
from backend.app.domain.sources import SourceReference, is_retrievable_source
from backend.app.embeddings.safety import source_city_applies
from backend.app.retrieval.models import DocumentChunk, RetrievalQuery

COMMUNITY_SOURCE_TYPES = {
    SourceType.verified_institutional_contributor,
    SourceType.verified_experienced_contributor,
    SourceType.ordinary_community,
}

HIGH_RISK_LEVELS = {
    RiskLevel.legal_sensitive,
    RiskLevel.work_status_sensitive,
    RiskLevel.medical_sensitive,
    RiskLevel.emergency,
}


def source_matches_query(source: SourceReference, query: RetrievalQuery) -> bool:
    if not is_retrievable_source(source):
        return False

    if query.source_pool == "official_curated" and source.source_type not in {
        SourceType.official, SourceType.curated_guide,
    }:
        return False
    if query.source_pool == "community" and source.source_type not in COMMUNITY_SOURCE_TYPES:
        return False

    if not query.include_community and source.source_type in COMMUNITY_SOURCE_TYPES:
        return False

    if query.risk_level in HIGH_RISK_LEVELS and source.source_type in COMMUNITY_SOURCE_TYPES:
        return False

    if query.scenario is not None and source.scenario not in {query.scenario, None}:
        return False

    if query.city is not None and not source_city_applies(source, query.city):
        return False

    if (
        query.language is not None
        and source.language != query.language
        and source.language.value != "unknown"
    ):
        return False

    return True


def filter_sources(
    sources: list[SourceReference],
    query: RetrievalQuery,
) -> list[SourceReference]:
    return [source for source in sources if source_matches_query(source, query)]


def filter_chunks(
    chunks: list[DocumentChunk],
    query: RetrievalQuery,
) -> list[DocumentChunk]:
    return [chunk for chunk in chunks if source_matches_query(chunk.source, query)]
