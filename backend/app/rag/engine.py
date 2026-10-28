from pathlib import Path
from typing import Any

from backend.app.answer_quality.composer import compose_grounded_answer
from backend.app.embeddings.safety import source_city_applies
from backend.app.hybrid_retrieval.models import (
    HybridRetrievalCandidate,
    HybridRetrievalRequest,
)
from backend.app.rag.fusion import reciprocal_rank_fusion
from backend.app.rag.models import (
    HybridEvidenceItem,
    HybridQueryRun,
    HybridRAGCoverage,
    HybridRAGRequest,
    HybridRAGResult,
)
from backend.app.rag.scoring import (
    COMMUNITY_SOURCE_TYPES,
    can_use_as_hybrid_evidence,
    score_source_for_query,
    source_type_rank,
)
from backend.app.retrieval.models import RetrievalQuery
from backend.app.retrieval.planner import (
    RetrievalPlan,
    RetrievalPlanningInput,
    build_retrieval_plan,
)
from backend.app.retrieval.quality import (
    RetrievalQualityInput,
    build_retrieval_quality_report,
    quality_report_to_jsonable,
)
from backend.app.retrieval.query_expansion import expand_retrieval_query
from backend.app.retrieval.service import RetrievalService
from backend.app.source_freshness.policies import (
    assess_source_freshness,
    freshness_warning_for_answer,
)
from backend.app.source_governance.passages import complete_source_text
from backend.app.source_registry.registry import SourceRegistry

try:
    from backend.app.domain.enums import LanguageCode, UserScenario
except ImportError:  # pragma: no cover - defensive for future module reshaping
    LanguageCode = None
    UserScenario = None


class HybridRAGEngine:
    def __init__(
        self,
        source_registry: SourceRegistry | None = None,
        retrieval_service: RetrievalService | None = None,
        semantic_retrieval_service: Any | None = None,
    ) -> None:
        self.source_registry = source_registry or SourceRegistry.from_data_dir(Path("data/sources"))
        self.retrieval_service = retrieval_service or RetrievalService(
            source_registry=self.source_registry
        )
        if semantic_retrieval_service is None:
            from backend.app.hybrid_retrieval.service import HybridRetrievalService

            semantic_retrieval_service = HybridRetrievalService(
                source_registry=self.source_registry,
                retrieval_service=self.retrieval_service,
            )
        self.semantic_retrieval_service = semantic_retrieval_service

    def build_request(
        self,
        user_message: str,
        scenario: str | None = None,
        risk_level: str | None = None,
        language: str | None = None,
        max_queries: int = 6,
        max_results_per_query: int = 6,
        max_evidence: int = 5,
        include_answer_draft: bool = True,
        use_semantic_retrieval: bool = False,
        semantic_top_k: int = 5,
        city: str | None = None,
    ) -> HybridRAGRequest:
        return HybridRAGRequest(
            user_message=user_message,
            scenario=scenario,
            risk_level=risk_level,
            language=language,
            max_queries=max_queries,
            max_results_per_query=max_results_per_query,
            max_evidence=max_evidence,
            include_answer_draft=include_answer_draft,
            use_semantic_retrieval=use_semantic_retrieval,
            semantic_top_k=semantic_top_k,
            city=city,
        )

    def run(self, request: HybridRAGRequest) -> HybridRAGResult:
        planning_input = RetrievalPlanningInput(
            user_message=request.user_message,
            scenario=request.scenario,
            risk_level=request.risk_level,
            language=request.language,
        )
        plan = build_retrieval_plan(planning_input)
        expansion = expand_retrieval_query(
            request.user_message,
            scenario=request.scenario,
            risk_level=request.risk_level,
            language=request.language,
        )
        domain = expansion.domain
        semantic_diagnostics: dict[str, Any] = {}
        semantic_warnings: list[str] = []
        if request.use_semantic_retrieval:
            query_runs, evidence, semantic_diagnostics = self._semantic_retrieval_evidence(
                request=request,
                plan=plan,
                domain=domain,
            )
            if not evidence and not getattr(
                self.semantic_retrieval_service, "strict_source_eligibility", False
            ):
                semantic_warnings.append(
                    "Semantic retrieval returned no trusted evidence; default Hybrid RAG "
                    "retrieval path was used as fallback."
                )
                semantic_diagnostics["fallback_to_default_retrieval"] = True
                query_runs, evidence = self._default_retrieval_evidence(
                    request=request,
                    plan=plan,
                    expanded_queries=expansion.expanded_queries,
                    domain=domain,
                )
        else:
            query_runs, evidence = self._default_retrieval_evidence(
                request=request,
                plan=plan,
                expanded_queries=expansion.expanded_queries,
                domain=domain,
            )

        evidence = _policy_safe_evidence_order(evidence, plan, domain)[: request.max_evidence]
        evidence = [
            item.model_copy(update={"rank": rank}) for rank, item in enumerate(evidence, start=1)
        ]
        coverage = self._build_coverage(evidence, plan, domain)
        quality_report = build_retrieval_quality_report(
            RetrievalQualityInput(
                user_message=request.user_message,
                scenario=request.scenario,
                risk_level=request.risk_level,
                language=request.language,
                expected_source_types=plan.required_source_types,
            ),
            evidence,
            plan=plan,
        )
        answer_draft = None
        if request.include_answer_draft:
            answer_draft = compose_grounded_answer(
                user_message=request.user_message,
                trusted_sources=evidence,
                scenario=request.scenario or domain,
                risk_level=request.risk_level,
                language=request.language,
                checklist_items=None,
                unreviewed_candidate_count=0,
            ).model_dump(mode="json")

        warnings = list(
            dict.fromkeys(
                [
                    *plan.warnings,
                    *coverage.warnings,
                    *coverage.freshness_warnings,
                    *quality_report.warnings,
                    *expansion.warnings,
                    *semantic_warnings,
                ]
            )
        )
        return HybridRAGResult(
            request=request,
            domain=domain,
            query_runs=query_runs,
            evidence=evidence,
            coverage=coverage,
            quality_report=quality_report_to_jsonable(quality_report),
            answer_draft=answer_draft,
            used_network=bool(semantic_diagnostics.get("used_network", False)),
            used_provider_call=bool(semantic_diagnostics.get("used_external_provider", False)),
            warnings=warnings,
            freshness_warnings=coverage.freshness_warnings,
            semantic_retrieval_enabled=request.use_semantic_retrieval,
            semantic_retrieval_diagnostics=semantic_diagnostics,
        )

    def _default_retrieval_evidence(
        self,
        request: HybridRAGRequest,
        plan: RetrievalPlan,
        expanded_queries: list[Any],
        domain: str,
    ) -> tuple[list[HybridQueryRun], list[HybridEvidenceItem]]:
        planned_runs = _planned_query_runs(request, plan, expanded_queries)
        ranked_lists: list[list[HybridEvidenceItem]] = []
        query_runs: list[HybridQueryRun] = []

        for query_run in planned_runs:
            evidence_items = self._run_query(
                query_run.query,
                plan,
                request,
                weight=query_run.weight,
                domain=domain,
            )
            ranked_lists.append(evidence_items)
            query_runs.append(
                query_run.model_copy(
                    update={
                        "retrieved_count": len(evidence_items),
                        "source_ids": [item.source_id for item in evidence_items],
                    }
                )
            )
        evidence = []
        for community_pool in (False, True):
            pool_lists = [
                _rank_query_evidence([
                    item for item in ranked
                    if (item.source_type in COMMUNITY_SOURCE_TYPES) == community_pool
                ])
                for ranked in ranked_lists
            ]
            evidence.extend(reciprocal_rank_fusion(pool_lists))
        return query_runs, evidence

    def _semantic_retrieval_evidence(
        self,
        request: HybridRAGRequest,
        plan: RetrievalPlan,
        domain: str,
    ) -> tuple[list[HybridQueryRun], list[HybridEvidenceItem], dict[str, Any]]:
        semantic_result = self.semantic_retrieval_service.retrieve(
            HybridRetrievalRequest(
                query=request.user_message,
                city=request.city,
                scenario=request.scenario,
                risk_level=request.risk_level,
                domain=domain,
                top_k=request.semantic_top_k,
                include_lexical=True,
                include_vector=True,
                require_trusted_sources=True,
                exclude_deprecated=True,
                exclude_unreviewed=True,
            )
        )
        diagnostics = semantic_result.diagnostics.model_dump(mode="json")
        diagnostics["semantic_enabled"] = True
        evidence: list[HybridEvidenceItem] = []
        for candidate in semantic_result.candidates:
            item = self._semantic_candidate_to_evidence(
                candidate=candidate,
                plan=plan,
                request=request,
                domain=domain,
            )
            if item is not None:
                evidence.append(item)
        evidence = _rank_query_evidence(evidence)
        query_run = HybridQueryRun(
            query=request.user_message,
            reason="semantic_hybrid_retrieval",
            weight=1.0,
            retrieved_count=len(evidence),
            source_ids=[item.source_id for item in evidence],
        )
        return [query_run], evidence, diagnostics

    def _semantic_candidate_to_evidence(
        self,
        candidate: HybridRetrievalCandidate,
        plan: RetrievalPlan,
        request: HybridRAGRequest,
        domain: str,
    ) -> HybridEvidenceItem | None:
        source = self.source_registry.get_source_by_id(candidate.source_id)
        if source is None:
            return None
        if request.city is not None and not source_city_applies(source, request.city):
            return None
        if not can_use_as_hybrid_evidence(source, domain, request.risk_level):
            return None
        if not _source_allowed_by_plan(source, plan):
            return None
        if candidate.source_version_status in {"deprecated", "superseded"}:
            return None
        freshness = assess_source_freshness(
            source,
            scenario=request.scenario,
            risk_level=request.risk_level,
            domain=domain,
        )
        if freshness.status == "deprecated":
            return None
        base_score = max(
            [
                float(candidate.fused_score or 0.0),
                float(candidate.lexical_score or 0.0),
                float(candidate.vector_score or 0.0),
            ]
        )
        score, reasons, warnings = score_source_for_query(
            source,
            query=request.user_message,
            base_score=base_score,
            domain=domain,
            risk_level=request.risk_level,
        )
        freshness_warning = freshness_warning_for_answer(freshness)
        freshness_warnings = [freshness_warning] if freshness_warning else []
        semantic_reasons = [
            "semantic_hybrid_retrieval",
            *(
                [f"semantic_lexical_rank:{candidate.lexical_rank}"]
                if candidate.lexical_rank
                else []
            ),
            *([f"semantic_vector_rank:{candidate.vector_rank}"] if candidate.vector_rank else []),
        ]
        excerpt = _excerpt_from_semantic_candidate(candidate, source)
        if not excerpt:
            return None
        return HybridEvidenceItem(
            source_id=candidate.source_id,
            chunk_id=candidate.chunk_id,
            version_id=candidate.version_id,
            title=candidate.title or str(getattr(source, "title", "Unknown source")),
            excerpt=excerpt,
            source_type=candidate.source_type or _enum_value(getattr(source, "source_type", None)),
            trust_level=candidate.trust_level or _enum_value(getattr(source, "trust_level", None)),
            rank=int(candidate.final_rank or 1),
            score=score,
            fused_score=float(candidate.fused_score or 0.0),
            lexical_score=candidate.lexical_score,
            vector_score=candidate.vector_score,
            rerank_score=candidate.rerank_score,
            retrieval_rank=(
                candidate.final_rank
                if getattr(self.semantic_retrieval_service, "strict_source_eligibility", False)
                else None
            ),
            used_for=_used_for(source),
            reasons=list(dict.fromkeys([*semantic_reasons, *reasons])),
            warnings=list(dict.fromkeys([*candidate.warnings, *warnings, *freshness_warnings])),
            freshness_status=candidate.freshness_status or freshness.status,
            source_version_status=candidate.source_version_status,
        )

    def _run_query(
        self,
        query: str,
        plan: RetrievalPlan,
        request: HybridRAGRequest,
        weight: float = 1.0,
        domain: str | None = None,
    ) -> list[HybridEvidenceItem]:
        active_domain = domain or str(plan.scenario or "general_life")
        retrieval_results = self.retrieval_service.retrieve(
            RetrievalQuery(
                query=query,
                scenario=_scenario_enum(request.scenario, active_domain),
                city=request.city,
                language=_language_enum(request.language),
                cross_language_official=True,
                include_community=_include_community_candidates(plan),
                max_results=request.max_results_per_query,
            )
        )
        evidence_items: list[HybridEvidenceItem] = []
        for result in retrieval_results:
            source = result.chunk.source
            if not can_use_as_hybrid_evidence(source, active_domain, request.risk_level):
                continue
            if not _source_allowed_by_plan(source, plan):
                continue
            excerpt = _excerpt_from_result(result)
            if not excerpt:
                continue
            score, reasons, warnings = score_source_for_query(
                source,
                query=query,
                base_score=float(result.score or 0.0),
                domain=active_domain,
                risk_level=request.risk_level,
            )
            freshness = assess_source_freshness(
                source,
                scenario=request.scenario,
                risk_level=request.risk_level,
                domain=active_domain,
            )
            if freshness.status == "deprecated":
                continue
            freshness_warning = freshness_warning_for_answer(freshness)
            freshness_warnings = [freshness_warning] if freshness_warning else []
            evidence_items.append(
                HybridEvidenceItem(
                    source_id=str(getattr(source, "source_id", "unknown")),
                    title=str(getattr(source, "title", "Unknown source")),
                    excerpt=excerpt,
                    source_type=_enum_value(getattr(source, "source_type", None)),
                    trust_level=_enum_value(getattr(source, "trust_level", None)),
                    rank=int(result.rank or len(evidence_items) + 1),
                    score=score * weight,
                    fused_score=0.0,
                    used_for=_used_for(source),
                    reasons=list(dict.fromkeys([*result.match_reasons, *reasons])),
                    warnings=list(dict.fromkeys([*warnings, *freshness_warnings])),
                    freshness_status=freshness.status,
                )
            )
        return _rank_query_evidence(evidence_items)

    def _build_coverage(
        self,
        evidence: list[HybridEvidenceItem],
        plan: RetrievalPlan,
        domain: str,
    ) -> HybridRAGCoverage:
        official_count = sum(1 for item in evidence if item.source_type == "official")
        curated_count = sum(1 for item in evidence if item.source_type == "curated_guide")
        community_count = sum(1 for item in evidence if item.source_type in COMMUNITY_SOURCE_TYPES)
        has_official_or_curated = official_count + curated_count > 0
        required_source_types = list(plan.required_source_types)
        has_policy_required_source = (
            True
            if not required_source_types
            else any(item.source_type in required_source_types for item in evidence)
        )
        warnings: list[str] = []
        freshness_warnings = [
            warning
            for item in evidence
            for warning in item.warnings
            if "freshness" in warning.casefold()
            or "stale" in warning.casefold()
            or "deprecated" in warning.casefold()
            or "needs refresh" in warning.casefold()
        ]
        fresh_count = sum(1 for item in evidence if item.freshness_status == "fresh")
        stale_count = sum(1 for item in evidence if item.freshness_status == "stale")
        unknown_count = sum(1 for item in evidence if item.freshness_status == "unknown")
        needs_refresh_count = sum(
            1
            for item in evidence
            if item.freshness_status in {"stale", "unknown", "needs_refresh", "deprecated"}
        )

        if not evidence:
            warnings.append("Hybrid RAG found no trusted local evidence for this request.")
        if plan.source_policy.require_official and official_count == 0:
            warnings.append("Hybrid RAG evidence lacks required official source coverage.")
        if plan.source_policy.require_official and not has_official_or_curated:
            warnings.append(
                "High-risk or official-required retrieval lacks official/curated support."
            )
        if community_count and _is_sensitive_context(domain, plan.risk_level):
            warnings.append(
                "Community evidence is practical context only and must not support official "
                "claims in this domain."
            )
        if not has_policy_required_source:
            warnings.append("Hybrid RAG evidence does not include the required source type.")

        return HybridRAGCoverage(
            trusted_evidence_count=len(evidence),
            official_count=official_count,
            curated_count=curated_count,
            community_count=community_count,
            has_official_or_curated=has_official_or_curated,
            has_policy_required_source=has_policy_required_source,
            warnings=list(dict.fromkeys([*warnings, *freshness_warnings])),
            freshness_warnings=list(dict.fromkeys(freshness_warnings)),
            fresh_count=fresh_count,
            stale_count=stale_count,
            unknown_count=unknown_count,
            needs_refresh_count=needs_refresh_count,
        )


def _planned_query_runs(
    request: HybridRAGRequest,
    plan: RetrievalPlan,
    expanded_queries: list[Any],
) -> list[HybridQueryRun]:
    runs: list[HybridQueryRun] = []
    seen_queries: set[str] = set()

    for expanded_query in expanded_queries:
        _append_query_run(
            runs,
            seen_queries,
            HybridQueryRun(
                query=expanded_query.query,
                reason=expanded_query.reason,
                weight=expanded_query.weight,
            ),
            max_queries=request.max_queries,
        )

    for plan_query in plan.queries:
        _append_query_run(
            runs,
            seen_queries,
            HybridQueryRun(
                query=plan_query.query,
                reason=f"retrieval_plan:{plan_query.intent}",
                weight=0.85 if plan_query.required else 0.75,
            ),
            max_queries=request.max_queries,
        )

    return runs


def _append_query_run(
    runs: list[HybridQueryRun],
    seen_queries: set[str],
    query_run: HybridQueryRun,
    max_queries: int,
) -> None:
    if len(runs) >= max_queries:
        return
    normalized_query = " ".join(query_run.query.casefold().split())
    if not normalized_query or normalized_query in seen_queries:
        return
    seen_queries.add(normalized_query)
    runs.append(query_run)


def _source_allowed_by_plan(source: Any, plan: RetrievalPlan) -> bool:
    source_type = _enum_value(getattr(source, "source_type", None))
    if source_type in set(plan.excluded_source_types):
        return False
    if source_type == "official":
        return True
    if source_type == "curated_guide":
        return plan.source_policy.allow_curated
    if source_type == "verified_institutional_contributor":
        return plan.source_policy.allow_verified_institutional
    if source_type == "verified_experienced_contributor":
        return plan.source_policy.allow_verified_experience
    if source_type == "ordinary_community":
        return plan.source_policy.allow_community
    return False


def _include_community_candidates(plan: RetrievalPlan) -> bool:
    return any(
        [
            plan.source_policy.allow_verified_institutional,
            plan.source_policy.allow_verified_experience,
            plan.source_policy.allow_community,
        ]
    )


def _rank_query_evidence(items: list[HybridEvidenceItem]) -> list[HybridEvidenceItem]:
    if any(item.retrieval_rank is not None for item in items):
        ranked = sorted(items, key=_semantic_evidence_key)
        return [item.model_copy(update={"rank": rank}) for rank, item in enumerate(ranked, 1)]
    sorted_items = sorted(
        items,
        key=lambda item: (
            source_type_rank(item.source_type, item.trust_level),
            -item.score,
            item.source_id,
        ),
    )
    return [item.model_copy(update={"rank": rank}) for rank, item in enumerate(sorted_items, 1)]


def _policy_safe_evidence_order(
    evidence: list[HybridEvidenceItem],
    plan: RetrievalPlan,
    domain: str,
) -> list[HybridEvidenceItem]:
    if any(item.retrieval_rank is not None for item in evidence):
        return sorted(evidence, key=_semantic_evidence_key)
    if not plan.source_policy.require_official and not _is_sensitive_context(
        domain,
        plan.risk_level,
    ):
        return evidence
    return sorted(
        evidence,
        key=lambda item: (
            source_type_rank(item.source_type, item.trust_level),
            -item.fused_score,
            -item.score,
            item.source_id,
        ),
    )


def _semantic_evidence_key(item: HybridEvidenceItem) -> tuple:
    """Provider relevance orders evidence within each immutable trust tier."""
    return (
        source_type_rank(item.source_type, item.trust_level),
        item.retrieval_rank if item.retrieval_rank is not None else 2**31,
        item.source_id,
        item.chunk_id or "",
    )


def _scenario_enum(scenario: str | None, domain: str) -> Any:
    if UserScenario is None:
        return None
    # Unclear is a routing sentinel, not a source scenario constraint.
    if scenario and scenario != UserScenario.unclear.value:
        try:
            return UserScenario(scenario)
        except ValueError:
            pass
    domain_map = {
        "passport_document_loss": "emergency",
        "emergency": "emergency",
        "visa_overstay_registration": "documents",
        "work_contract_status": "work",
        "medical_hospital": "medical",
        "payment_scam": "payments",
        "housing_registration": "housing",
        "study_university": "study",
    }
    mapped = domain_map.get(domain)
    return UserScenario(mapped) if mapped else None


def _language_enum(language: str | None) -> Any:
    if LanguageCode is None or language in {None, "en", "unknown"}:
        return None
    try:
        return LanguageCode(language)
    except ValueError:
        return None


def _excerpt_from_result(result: Any) -> str:
    chunk = getattr(result, "chunk", None)
    source = getattr(chunk, "source", None)
    if source is not None and source.content:
        return complete_source_text(source)
    content = str(getattr(chunk, "content", "") or "")
    return content if len(content) <= 2400 else ""


def _excerpt_from_semantic_candidate(
    candidate: HybridRetrievalCandidate,
    source: Any,
) -> str:
    # A retrieval preview is a search aid, never a complete answer passage.
    del candidate
    return complete_source_text(source)


def _used_for(source: Any) -> str:
    source_type = _enum_value(getattr(source, "source_type", None))
    return "grounding" if source_type in {"official", "curated_guide"} else "practical_context"


def _is_sensitive_context(domain: str, risk_level: str | None) -> bool:
    return domain in {
        "passport_document_loss",
        "visa_overstay_registration",
        "work_contract_status",
        "medical_hospital",
        "emergency",
    } or (risk_level or "").casefold() in {
        "high",
        "legal_sensitive",
        "work_status_sensitive",
        "medical_sensitive",
        "emergency",
        "unsafe",
    }


def _enum_value(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)
