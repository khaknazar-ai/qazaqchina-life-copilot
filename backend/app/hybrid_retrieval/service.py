from pathlib import Path
from typing import Any

from backend.app.domain.enums import RiskLevel, UserScenario
from backend.app.domain.sources import SourceReference, is_retrievable_source
from backend.app.embeddings.models import EmbeddingProviderConfig, EmbeddingRequest
from backend.app.embeddings.providers import FakeEmbeddingProvider
from backend.app.embeddings.safety import source_city_applies
from backend.app.embeddings.service import EmbeddingService
from backend.app.hybrid_retrieval.fusion import (
    fuse_candidates,
    merge_lexical_and_vector_candidates,
)
from backend.app.hybrid_retrieval.models import (
    HybridRetrievalCandidate,
    HybridRetrievalDiagnostics,
    HybridRetrievalRequest,
    HybridRetrievalResult,
)
from backend.app.rag.scoring import (
    COMMUNITY_SOURCE_TYPES,
    source_policy_warnings,
)
from backend.app.retrieval.models import RetrievalQuery
from backend.app.retrieval.query_expansion import expand_retrieval_query
from backend.app.retrieval.service import RetrievalService
from backend.app.source_freshness.policies import (
    assess_source_freshness,
    freshness_warning_for_answer,
)
from backend.app.source_index.service import SourceIndexService
from backend.app.source_registry.registry import SourceRegistry
from backend.app.vector_index.local_index import LocalVectorIndex
from backend.app.vector_index.models import VectorSearchFilter, VectorSearchRequest

_DEPRECATED_STATUSES = {"deprecated", "superseded"}
_UNREVIEWED_SOURCE_TYPES = {"untrusted", "candidate", "unreviewed_candidate"}
_UNREVIEWED_TRUST_LEVELS = {"level_6_untrusted", "untrusted"}
_TRUSTED_SOURCE_TYPES = {
    "official",
    "curated_guide",
    "verified_institutional_contributor",
    "verified_experienced_contributor",
    "ordinary_community",
}
_SCENARIO_MAP = {
    "lost-passport-emergency": UserScenario.emergency,
    "study-registration": UserScenario.study,
    "unsafe-work-status": UserScenario.work,
    "payment-scam-warning": UserScenario.payments,
    "housing-registration": UserScenario.housing,
    "hospital-registration": UserScenario.medical,
    "police-station-registration": UserScenario.housing,
    "visa-extension-warning": UserScenario.documents,
    "bank-card-payment-setup": UserScenario.payments,
    "sim-card-registration": UserScenario.documents,
    "work-contract-risk": UserScenario.work,
    "university-dormitory-issue": UserScenario.study,
    "lost-phone-and-documents": UserScenario.emergency,
    "consulate-appointment-flow": UserScenario.emergency,
    "community-misinformation-conflict": UserScenario.work,
    "passport_document_loss": UserScenario.emergency,
    "visa_overstay_registration": UserScenario.documents,
    "work_contract_status": UserScenario.work,
    "medical_hospital": UserScenario.medical,
    "payment_scam": UserScenario.payments,
    "study_university": UserScenario.study,
}
_HIGH_RISK_VALUES = {
    "high",
    "legal_sensitive",
    "work_status_sensitive",
    "medical_sensitive",
    "emergency",
    "unsafe",
    "prompt_injection",
}
_HIGH_RISK_DOMAINS = {
    "passport_document_loss",
    "visa_overstay_registration",
    "work_contract_status",
    "medical_hospital",
    "emergency",
}


class HybridRetrievalService:
    def __init__(
        self,
        source_registry: SourceRegistry | None = None,
        retrieval_service: RetrievalService | None = None,
        embedding_dimensions: int = 16,
    ) -> None:
        self.source_registry = source_registry or SourceRegistry.from_data_dir(
            Path("data/sources")
        )
        self.retrieval_service = retrieval_service or RetrievalService(
            source_registry=self.source_registry
        )
        self.embedding_dimensions = embedding_dimensions

    def retrieve(self, request: HybridRetrievalRequest) -> HybridRetrievalResult:
        active_domain = _domain_for_request(request)
        lexical_raw = self.lexical_candidates(request) if request.include_lexical else []
        vector_raw = self.vector_candidates(request) if request.include_vector else []
        lexical_candidates, lexical_counts = _apply_candidate_filters(
            lexical_raw,
            request,
            active_domain,
        )
        vector_candidates, vector_counts = _apply_candidate_filters(
            vector_raw,
            request,
            active_domain,
        )
        fused = []
        for community_pool in (False, True):
            merged = merge_lexical_and_vector_candidates(
                [c for c in lexical_candidates
                 if (c.source_type in COMMUNITY_SOURCE_TYPES) == community_pool],
                [c for c in vector_candidates
                 if (c.source_type in COMMUNITY_SOURCE_TYPES) == community_pool],
            )
            fused.extend(fuse_candidates(merged, top_k=request.top_k))
        fused = [candidate.model_copy(update={"final_rank": rank})
                 for rank, candidate in enumerate(fused[:request.top_k], start=1)]
        diagnostics = _build_diagnostics(
            request=request,
            domain=active_domain,
            lexical_candidates=lexical_candidates,
            vector_candidates=vector_candidates,
            fused=fused,
            deprecated_excluded_count=(
                lexical_counts["deprecated_excluded_count"]
                + vector_counts["deprecated_excluded_count"]
            ),
            unreviewed_excluded_count=(
                lexical_counts["unreviewed_excluded_count"]
                + vector_counts["unreviewed_excluded_count"]
            ),
        )
        return HybridRetrievalResult(
            request=request,
            candidates=fused,
            diagnostics=diagnostics,
        )

    def lexical_candidates(
        self,
        request: HybridRetrievalRequest,
    ) -> list[HybridRetrievalCandidate]:
        active_domain = _domain_for_request(request)
        results = [result for pool in ("official_curated", "community")
                   for result in self.retrieval_service.retrieve(
            RetrievalQuery(
                query=request.query,
                scenario=_scenario_enum(request.scenario, active_domain),
                city=request.city,
                risk_level=_risk_enum(request.risk_level),
                include_community=True,
                source_pool=pool,
                max_results=max(request.top_k * 3, request.top_k),
            )
        )]
        candidates: list[HybridRetrievalCandidate] = []
        for result in results:
            source = result.chunk.source
            freshness = assess_source_freshness(
                source,
                scenario=request.scenario,
                risk_level=request.risk_level,
                domain=active_domain,
            )
            freshness_warning = freshness_warning_for_answer(freshness)
            warnings = _unique(
                [
                    *source_policy_warnings(source, active_domain, request.risk_level),
                    *([freshness_warning] if freshness_warning else []),
                ]
            )
            candidates.append(
                HybridRetrievalCandidate(
                    candidate_id=str(getattr(source, "source_id", "unknown")),
                    source_id=str(getattr(source, "source_id", "unknown")),
                    chunk_id=result.chunk.chunk_id,
                    title=str(getattr(source, "title", "")) or None,
                    text_preview=_preview(result.chunk.content),
                    source_type=_enum_value(getattr(source, "source_type", None)),
                    trust_level=_enum_value(getattr(source, "trust_level", None)),
                    freshness_status=freshness.status,
                    lexical_rank=int(result.rank or len(candidates) + 1),
                    lexical_score=float(result.score or 0.0),
                    retrievable=_source_retrievable(source),
                    indexable=_source_retrievable(source),
                    warnings=warnings,
                )
            )
        return candidates

    def vector_candidates(
        self,
        request: HybridRetrievalRequest,
    ) -> list[HybridRetrievalCandidate]:
        source_index = SourceIndexService().build_index_from_sources(
            self.source_registry.all_sources()
        )
        chunks_by_id = {chunk.chunk_id: chunk for chunk in source_index.chunks}
        sources_by_id = {
            str(getattr(source, "source_id", "unknown")): source
            for source in self.source_registry.all_sources()
        }
        embedding_manifest = EmbeddingService().embed_chunks(
            source_index.chunks,
            config=EmbeddingProviderConfig(dimensions=self.embedding_dimensions),
            include_non_indexable=True,
        )
        query_response = FakeEmbeddingProvider().embed_texts(
            EmbeddingRequest(
                texts=[request.query],
                dimensions=self.embedding_dimensions,
            )
        )
        scoped_records = [record for record in embedding_manifest.records
                          if request.city is None or source_city_applies(
                              sources_by_id[record.source_id], request.city,
                          )]
        search_results = []
        for community_pool in (False, True):
            local_index = LocalVectorIndex([
                record for record in scoped_records
                if (record.source_type in COMMUNITY_SOURCE_TYPES) == community_pool
            ])
            search_results.extend(local_index.search(
            VectorSearchRequest(
                query_vector=query_response.vectors[0],
                top_k=max(request.top_k * 4, request.top_k),
                filters=VectorSearchFilter(
                    require_indexable=False,
                    require_retrievable=False,
                ),
            )
        ))
        candidates: list[HybridRetrievalCandidate] = []
        active_domain = _domain_for_request(request)
        for result in search_results:
            chunk = chunks_by_id.get(result.chunk_id)
            source = sources_by_id.get(result.source_id)
            warnings = list(result.warnings)
            if source is not None:
                warnings.extend(
                    source_policy_warnings(source, active_domain, request.risk_level)
                )
            candidates.append(
                HybridRetrievalCandidate(
                    candidate_id=result.source_id,
                    source_id=result.source_id,
                    chunk_id=result.chunk_id,
                    version_id=result.version_id,
                    title=_source_title(source),
                    text_preview=_preview(chunk.text if chunk else ""),
                    source_type=result.source_type,
                    trust_level=result.trust_level,
                    freshness_status=result.freshness_status,
                    source_version_status=result.source_version_status,
                    vector_rank=result.rank,
                    vector_score=result.score,
                    retrievable=bool(result.metadata.get("retrievable", True)),
                    indexable=bool(result.metadata.get("indexable", True)),
                    warnings=_unique(warnings),
                )
            )
        return candidates


def result_to_jsonable(result: HybridRetrievalResult) -> dict:
    return result.model_dump(mode="json")


def result_to_markdown(result: HybridRetrievalResult) -> str:
    diagnostics = result.diagnostics
    lines = [
        "# Hybrid Lexical + Vector Retrieval Inspection",
        "",
        f"- Query: {result.request.query}",
        f"- Scenario: {result.request.scenario or 'none'}",
        f"- Risk level: {result.request.risk_level or 'none'}",
        f"- Domain: {result.request.domain or _domain_for_request(result.request)}",
        f"- Lexical results: {diagnostics.lexical_result_count}",
        f"- Vector results: {diagnostics.vector_result_count}",
        f"- Fused results: {diagnostics.fused_result_count}",
        f"- Official sources: {diagnostics.official_count}",
        f"- Curated guides: {diagnostics.curated_count}",
        f"- Community sources: {diagnostics.community_count}",
        f"- Used network: {diagnostics.used_network}",
        f"- Used external provider: {diagnostics.used_external_provider}",
        f"- Used external vector DB: {diagnostics.used_external_vector_db}",
        "",
        "No /api/chat integration.",
        "",
        "## Candidates",
    ]
    if not result.candidates:
        lines.append("- none")
    else:
        for candidate in result.candidates:
            lines.append(
                "- "
                f"{candidate.final_rank}. {candidate.source_id} "
                f"({candidate.source_type or 'unknown'}) "
                f"fused_score={candidate.fused_score:.6f}"
            )
    lines.extend(["", "## Warnings"])
    if diagnostics.warnings:
        lines.extend(f"- {warning}" for warning in diagnostics.warnings)
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def _apply_candidate_filters(
    candidates: list[HybridRetrievalCandidate],
    request: HybridRetrievalRequest,
    domain: str,
) -> tuple[list[HybridRetrievalCandidate], dict[str, int]]:
    filtered: list[HybridRetrievalCandidate] = []
    counts = {
        "deprecated_excluded_count": 0,
        "unreviewed_excluded_count": 0,
    }
    for candidate in candidates:
        if request.exclude_deprecated and _candidate_deprecated(candidate):
            counts["deprecated_excluded_count"] += 1
            continue
        if request.exclude_unreviewed and _candidate_unreviewed(candidate):
            counts["unreviewed_excluded_count"] += 1
            continue
        if request.require_trusted_sources and not _candidate_trusted(candidate):
            counts["unreviewed_excluded_count"] += 1
            continue
        if request.require_trusted_sources and not _policy_allows_candidate(
            candidate,
            domain,
            request.risk_level,
        ):
            counts["unreviewed_excluded_count"] += 1
            continue
        filtered.append(candidate)
    return filtered, counts


def _build_diagnostics(
    request: HybridRetrievalRequest,
    domain: str,
    lexical_candidates: list[HybridRetrievalCandidate],
    vector_candidates: list[HybridRetrievalCandidate],
    fused: list[HybridRetrievalCandidate],
    deprecated_excluded_count: int,
    unreviewed_excluded_count: int,
) -> HybridRetrievalDiagnostics:
    official_count = sum(1 for candidate in fused if candidate.source_type == "official")
    curated_count = sum(1 for candidate in fused if candidate.source_type == "curated_guide")
    community_count = sum(
        1 for candidate in fused if candidate.source_type in COMMUNITY_SOURCE_TYPES
    )
    warnings = _unique([warning for candidate in fused for warning in candidate.warnings])
    if _requires_official_or_curated(request, domain) and official_count + curated_count == 0:
        warnings.append(
            "High-risk hybrid retrieval found no official or curated candidates."
        )
    return HybridRetrievalDiagnostics(
        lexical_result_count=len(lexical_candidates),
        vector_result_count=len(vector_candidates),
        fused_result_count=len(fused),
        official_count=official_count,
        curated_count=curated_count,
        community_count=community_count,
        stale_count=sum(1 for candidate in fused if candidate.freshness_status == "stale"),
        unknown_freshness_count=sum(
            1 for candidate in fused if candidate.freshness_status == "unknown"
        ),
        deprecated_excluded_count=deprecated_excluded_count,
        unreviewed_excluded_count=unreviewed_excluded_count,
        used_network=False,
        used_external_provider=False,
        used_external_vector_db=False,
        warnings=warnings,
    )


def _domain_for_request(request: HybridRetrievalRequest) -> str:
    if request.domain:
        return request.domain
    return expand_retrieval_query(
        request.query,
        scenario=request.scenario,
        risk_level=request.risk_level,
    ).domain


def _scenario_enum(scenario: str | None, domain: str) -> UserScenario | None:
    for value in [scenario, domain]:
        if not value:
            continue
        try:
            return UserScenario(value)
        except ValueError:
            mapped = _SCENARIO_MAP.get(value)
            if mapped:
                return mapped
    return None


def _risk_enum(risk_level: str | None) -> RiskLevel | None:
    if not risk_level:
        return None
    try:
        return RiskLevel(risk_level)
    except ValueError:
        return None


def _candidate_deprecated(candidate: HybridRetrievalCandidate) -> bool:
    return (
        _normalize(candidate.freshness_status) == "deprecated"
        or _normalize(candidate.source_version_status) in _DEPRECATED_STATUSES
    )


def _candidate_unreviewed(candidate: HybridRetrievalCandidate) -> bool:
    return (
        _normalize(candidate.source_type) in _UNREVIEWED_SOURCE_TYPES
        or _normalize(candidate.trust_level) in _UNREVIEWED_TRUST_LEVELS
        or not candidate.retrievable
        or not candidate.indexable
    )


def _candidate_trusted(candidate: HybridRetrievalCandidate) -> bool:
    return _normalize(candidate.source_type) in _TRUSTED_SOURCE_TYPES


def _policy_allows_candidate(
    candidate: HybridRetrievalCandidate,
    domain: str,
    risk_level: str | None,
) -> bool:
    del domain, risk_level
    return candidate.retrievable and _candidate_trusted(candidate)


def _requires_official_or_curated(
    request: HybridRetrievalRequest,
    domain: str,
) -> bool:
    return (
        _normalize(request.risk_level) in _HIGH_RISK_VALUES
        or _normalize(domain) in _HIGH_RISK_DOMAINS
    )


def _source_retrievable(source: Any) -> bool:
    if isinstance(source, SourceReference):
        return is_retrievable_source(source)
    return bool(getattr(source, "allow_ai_retrieval", True))


def _source_title(source: Any | None) -> str | None:
    if source is None:
        return None
    title = str(getattr(source, "title", "")).strip()
    return title or None


def _preview(text: str | None, limit: int = 320) -> str | None:
    normalized = " ".join((text or "").split())
    if not normalized:
        return None
    return normalized[:limit]


def _enum_value(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def _normalize(value: str | None) -> str:
    return (value or "").casefold()


def _unique(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        if value and value not in deduped:
            deduped.append(value)
    return deduped
