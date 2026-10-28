from backend.app.agent.classification import (
    classify_risk,
    classify_scenario,
    has_active_prompt_injection,
    quoted_translation_content,
)
from backend.app.agent.policies import contains_unsafe_work_advice
from backend.app.agent.tool_control import run_controlled_offline_tool_discovery
from backend.app.answer_quality.composer import (
    compose_grounded_answer,
    render_grounded_answer_markdown,
)
from backend.app.answer_quality.diagnostics import build_answer_quality_report
from backend.app.checklist_engine.service import ChecklistEngineService
from backend.app.domain.agent import AgentState, UserProfileSnapshot
from backend.app.domain.enums import EscalationReason, LanguageCode, RiskLevel, UserScenario
from backend.app.domain.sources import Citation, RetrievedSource
from backend.app.escalation.service import EscalationService
from backend.app.multilingual.detection import detect_language
from backend.app.multilingual.policies import choose_response_language
from backend.app.multilingual.templates import format_agent_answer
from backend.app.retrieval.models import RetrievalQuery
from backend.app.retrieval.service import RetrievalService
from backend.app.source_governance.policies import (
    is_community_or_contributor_source,
    requires_official_or_curated_sources,
)
from backend.app.source_governance.service import SourceGovernanceService

KAZAKH_SPECIFIC_CHARS = set("әғқңөұүһі")
COMMUNITY_EXCLUDED_RISK_LEVELS = {
    RiskLevel.legal_sensitive,
    RiskLevel.work_status_sensitive,
    RiskLevel.medical_sensitive,
    RiskLevel.emergency,
    RiskLevel.unsafe,
    RiskLevel.prompt_injection,
}


def input_guard_node(state: AgentState) -> AgentState:
    if quoted_translation_content(state.user_message):
        _append_unique(state.safety_flags, "untrusted_translation_content")
    if has_active_prompt_injection(state.user_message):
        _append_unique(state.safety_flags, "prompt_injection")
        state.risk_level = RiskLevel.prompt_injection

    if classify_scenario(state.user_message) == UserScenario.work and contains_unsafe_work_advice(
        state.user_message
    ):
        _append_unique(state.safety_flags, "unsafe_work_advice")

    return state


def language_detector_node(state: AgentState) -> AgentState:
    detected_language = detect_language(state.user_message)
    preferred_language = getattr(state, "preferred_language", None) or (
        state.user_profile.preferred_language if state.user_profile else None
    )
    state.detected_language = detected_language
    state.response_language = choose_response_language(detected_language, preferred_language)
    return state


def profile_extraction_node(state: AgentState) -> AgentState:
    city = getattr(state, "city", None) or _extract_city(state.user_message)
    existing_profile = state.user_profile or UserProfileSnapshot(user_id=state.user_id)
    state.user_profile = existing_profile.model_copy(update={"city": city or existing_profile.city})
    return state


def scenario_router_node(state: AgentState) -> AgentState:
    state.scenario = classify_scenario(state.user_message)
    followup = getattr(state, "followup_scenario", None)
    if followup and state.scenario == UserScenario.unclear:
        state.scenario = followup
    return state


def risk_classifier_node(state: AgentState) -> AgentState:
    risk = classify_risk(state.user_message, state.scenario)
    if "prompt_injection" in state.safety_flags:
        risk = RiskLevel.prompt_injection
    elif "unsafe_work_advice" in state.safety_flags and state.scenario == UserScenario.work:
        if risk not in {RiskLevel.emergency, RiskLevel.unsafe, RiskLevel.prompt_injection}:
            risk = RiskLevel.work_status_sensitive
    inherited = getattr(state, "followup_risk_level", None)
    priority = {
        RiskLevel.normal: 0,
        RiskLevel.medium: 1,
        RiskLevel.legal_sensitive: 2,
        RiskLevel.work_status_sensitive: 2,
        RiskLevel.medical_sensitive: 2,
        RiskLevel.emergency: 3,
        RiskLevel.unsafe: 4,
        RiskLevel.prompt_injection: 5,
    }
    if inherited and priority[inherited] > priority[risk]:
        risk = inherited
    state.risk_level = risk
    if risk == RiskLevel.prompt_injection:
        _append_unique(state.safety_flags, "prompt_injection")
    return state


def retrieval_planner_node(state: AgentState) -> AgentState:
    if state.risk_level in {
        RiskLevel.legal_sensitive,
        RiskLevel.work_status_sensitive,
        RiskLevel.medical_sensitive,
        RiskLevel.emergency,
    }:
        _append_unique(state.safety_flags, "official_curated_priority")
    elif state.risk_level == RiskLevel.normal:
        _append_unique(state.safety_flags, "approved_community_context_allowed")
    return state


def retrieval_node(
    state: AgentState,
    retrieval_service: RetrievalService | None = None,
) -> AgentState:
    service = retrieval_service or RetrievalService()
    query = _retrieval_query_from_state(state)
    results = service.retrieve(query)
    from backend.app.source_governance.passages import complete_source_text

    state.selected_sources = [
        RetrievedSource(
            source=result.chunk.source,
            chunk_id=result.chunk.chunk_id,
            content=complete_source_text(result.chunk.source) or result.chunk.content,
            score=result.score,
            rank=result.rank,
        )
        for result in results
        if complete_source_text(result.chunk.source)
        or (not result.chunk.source.content and len(result.chunk.content) <= 2400)
    ]
    return state


def source_selection_stub_node(
    state: AgentState,
    retrieval_service: RetrievalService | None = None,
) -> AgentState:
    return retrieval_node(state, retrieval_service=retrieval_service)


def tool_decision_node(state: AgentState) -> AgentState:
    city = state.user_profile.city if state.user_profile else None
    result = run_controlled_offline_tool_discovery(
        user_message=state.user_message,
        scenario=state.scenario.value,
        risk_level=state.risk_level.value,
        language=state.detected_language.value
        if state.detected_language != LanguageCode.unknown
        else None,
        city=city,
    )
    state.tool_decision = result.decision.model_dump(mode="json")
    state.tool_trace = result.trace_payload
    state.unreviewed_source_candidate_count = result.source_candidate_count
    return state


def tool_execution_stub_node(state: AgentState) -> AgentState:
    if state.scenario == UserScenario.emergency:
        state.draft_answer = "Emergency helper stub selected."
    elif state.scenario == UserScenario.translation:
        state.draft_answer = "Translation explainer stub selected."
    elif state.risk_level in {RiskLevel.prompt_injection, RiskLevel.unsafe}:
        state.draft_answer = "Safe refusal stub selected."
    else:
        state.draft_answer = "Checklist or answer stub selected."
    return state


def answer_generation_stub_node(state: AgentState) -> AgentState:
    base = (
        "Deterministic Phase 11 retrieval-assisted workflow stub. No real LangGraph, "
        "no embeddings, no vector DB, no real RAG, and no real external LLM were used."
    )

    if state.risk_level == RiskLevel.prompt_injection:
        state.draft_answer = (
            f"{base} I cannot follow instructions that attempt to override system behavior "
            "or reveal secrets."
        )
    elif "unsafe_work_advice" in state.safety_flags:
        state.draft_answer = (
            f"{base} I cannot validate unsafe work-status advice. Verify official "
            "requirements and contact a qualified human or official source."
        )
    elif state.risk_level == RiskLevel.work_status_sensitive:
        state.draft_answer = (
            f"{base} This is work-status sensitive. Verify official requirements before "
            f"starting work and escalate to a qualified human if documents are unclear."
            " Sources are for general context; verify official requirements."
        )
    elif state.risk_level == RiskLevel.emergency:
        state.draft_answer = (
            f"{base} Take immediate safe steps, prepare key facts, and contact official "
            "or trusted human support. Sources are for general context; "
            "verify official requirements."
        )
    elif state.scenario == UserScenario.translation:
        state.draft_answer = f"{base} This is not real translation yet."
    else:
        state.draft_answer = (
            f"{base} Scenario '{state.scenario.value}' was routed by deterministic rules."
        )

    state.draft_answer = format_agent_answer(
        base_answer=state.draft_answer,
        language=state.response_language,
        risk_level=state.risk_level,
        source_ids=_selected_source_ids(state),
        community_source_used=_community_source_used(state),
        escalation_required=state.risk_level
        in {
            RiskLevel.legal_sensitive,
            RiskLevel.work_status_sensitive,
            RiskLevel.medical_sensitive,
            RiskLevel.emergency,
            RiskLevel.unsafe,
            RiskLevel.prompt_injection,
        },
    )
    return state


def citation_stub_node(state: AgentState) -> AgentState:
    unique_sources = _unique_retrieved_sources(state.selected_sources)
    state.citations = [
        Citation(
            citation_id=f"CIT-{index}",
            source_id=retrieved_source.source.source_id,
            claim=(
                f"Selected source supports the general scenario context for {state.scenario.value}."
            ),
            supporting_quote=retrieved_source.content,
            confidence=0.6,
        )
        for index, retrieved_source in enumerate(unique_sources[:3], start=1)
    ]
    return state


def source_governance_node(
    state: AgentState,
    source_governance_service: SourceGovernanceService | None = None,
) -> AgentState:
    service = source_governance_service or SourceGovernanceService()
    result = service.check(
        answer=state.draft_answer or "",
        selected_sources=state.selected_sources,
        citations=state.citations,
        risk_level=state.risk_level,
        safety_flags=state.safety_flags,
    )
    if result.passed:
        return state

    _append_unique(state.safety_flags, "source_governance_failed")
    _append_unique(state.safety_flags, "source_conflict")
    for finding in result.conflict_report.findings:
        _append_unique(state.errors, f"{finding.conflict_type}: {finding.summary}")
    for finding in result.citation_report.findings:
        _append_unique(state.errors, f"{finding.finding_type}: {finding.summary}")
    return state


def escalation_decider_node(
    state: AgentState,
    escalation_service: EscalationService | None = None,
) -> AgentState:
    service = escalation_service or EscalationService()
    plan = service.build_plan_from_state(state)
    state.escalation_required = plan.escalation_required
    state.escalation_summary = plan.handoff_summary
    if plan.escalation_required:
        _append_unique(state.safety_flags, "human_escalation_required")
    reasons: list[EscalationReason] = []

    for trigger in plan.triggers:
        reason = _escalation_reason_from_trigger(trigger.reason)
        if reason is not None:
            reasons.append(reason)
    if state.scenario == UserScenario.unclear:
        reasons.append(EscalationReason.low_confidence)

    state.escalation_reasons = list(dict.fromkeys(reasons))
    return state


def generate_checklist_node(
    state: AgentState,
    checklist_engine_service: ChecklistEngineService | None = None,
) -> AgentState:
    if state.scenario not in {
        UserScenario.tourism,
        UserScenario.kazakhstan_entry,
        UserScenario.study,
        UserScenario.work,
        UserScenario.medical,
        UserScenario.emergency,
        UserScenario.payments,
        UserScenario.housing,
    }:
        return state

    service = checklist_engine_service or ChecklistEngineService()
    result = service.generate_for_scenario(
        scenario=state.scenario,
        risk_level=state.risk_level,
        language=state.response_language,
        user_profile=state.user_profile,
        selected_source_ids=_selected_source_ids(state),
        safety_flags=state.safety_flags,
    )
    state.checklist = result.checklist
    for warning in result.warnings:
        _append_unique(state.errors, f"checklist_validation: {warning}")
    return state


def grounded_answer_quality_node(state: AgentState) -> AgentState:
    checklist_items = (
        [item.title for item in state.checklist.items] if state.checklist is not None else []
    )
    draft = compose_grounded_answer(
        user_message=state.user_message,
        trusted_sources=state.selected_sources,
        scenario=state.scenario.value,
        risk_level=state.risk_level.value,
        language=state.response_language.value,
        checklist_items=checklist_items,
        unreviewed_candidate_count=state.unreviewed_source_candidate_count,
    )
    report = build_answer_quality_report(draft)
    state.grounded_answer = draft.model_dump(mode="json")
    state.answer_quality_report = report.model_dump(mode="json")
    state.draft_answer = render_grounded_answer_markdown(draft)
    return state


def final_response_node(state: AgentState) -> AgentState:
    if state.final_answer is None:
        state.final_answer = state.draft_answer or (
            "Deterministic Phase 8 workflow stub produced no draft answer."
        )
    return state


def _detect_language(text: str) -> LanguageCode:
    lowered = text.casefold()
    if any("\u4e00" <= character <= "\u9fff" for character in text):
        return LanguageCode.zh
    if any(character in KAZAKH_SPECIFIC_CHARS for character in lowered):
        return LanguageCode.kk
    if any("\u0400" <= character <= "\u04ff" for character in text):
        return LanguageCode.ru
    if any(character.isascii() and character.isalpha() for character in text):
        return LanguageCode.en
    return LanguageCode.unknown


def _extract_city(text: str) -> str | None:
    normalized = text.casefold()
    city_patterns = {
        "Shanghai": ("shanghai", "шанхай", "上海"),
        "Hangzhou": ("hangzhou", "ханчжоу", "杭州"),
        "Beijing": ("beijing", "пекин", "北京"),
        "Guangzhou": ("guangzhou", "гуанчжоу", "广州"),
    }
    for city, patterns in city_patterns.items():
        if any(pattern in normalized for pattern in patterns):
            return city
    return None


def _contains_any(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)


def _retrieval_query_from_state(state: AgentState) -> RetrievalQuery:
    scenario = state.scenario if state.scenario != UserScenario.unclear else None
    city = state.user_profile.city if state.user_profile else None
    language = (
        state.detected_language
        if state.detected_language not in {LanguageCode.unknown, LanguageCode.en}
        else None
    )
    include_community = state.risk_level not in COMMUNITY_EXCLUDED_RISK_LEVELS
    return RetrievalQuery(
        query=state.user_message,
        scenario=scenario,
        city=city,
        language=language,
        cross_language_official=True,
        risk_level=state.risk_level,
        include_community=include_community,
        max_results=3,
    )


def _selected_sources_text(state: AgentState) -> str:
    if not state.selected_sources:
        return ""
    unique_sources = _unique_retrieved_sources(state.selected_sources)
    source_ids = ", ".join(retrieved_source.source.source_id for retrieved_source in unique_sources)
    source_text = f" Selected local sources: {source_ids}."
    if any(is_community_or_contributor_source(source.source) for source in unique_sources):
        source_text += (
            " Community/contributor sources are practical or institutional experience, "
            "not official law."
        )
    if requires_official_or_curated_sources(state.risk_level):
        source_text += " Official/curated sources should be prioritized for this risk level."
    return source_text


def _selected_source_ids(state: AgentState) -> list[str]:
    return [
        retrieved_source.source.source_id
        for retrieved_source in _unique_retrieved_sources(state.selected_sources)
    ]


def _community_source_used(state: AgentState) -> bool:
    return any(
        is_community_or_contributor_source(retrieved_source.source)
        for retrieved_source in _unique_retrieved_sources(state.selected_sources)
    )


def _unique_retrieved_sources(selected_sources: list[RetrievedSource]) -> list[RetrievedSource]:
    unique_sources: list[RetrievedSource] = []
    seen_source_ids: set[str] = set()
    for retrieved_source in selected_sources:
        source_id = retrieved_source.source.source_id
        if source_id in seen_source_ids:
            continue
        unique_sources.append(retrieved_source)
        seen_source_ids.add(source_id)
    return unique_sources


def _append_unique(items: list[str], item: str) -> None:
    if item not in items:
        items.append(item)


def _escalation_reason_from_trigger(reason: str) -> EscalationReason | None:
    if reason == "emergency":
        return EscalationReason.emergency
    if reason == "legal_sensitive":
        return EscalationReason.legal_sensitive
    if reason == "work_status_sensitive":
        return EscalationReason.work_status_sensitive
    if reason == "medical_sensitive":
        return EscalationReason.medical_sensitive
    if reason in {"safety_risk", "prompt_injection", "unsafe", "unsafe_work_advice"}:
        return EscalationReason.safety_risk
    if reason in {
        "source_governance_failed",
        "source_conflict",
        "missing_official_source",
        "high_risk_without_official_source",
        "citation_verification_failed",
    }:
        return EscalationReason.source_conflict
    if reason == "missing_information":
        return EscalationReason.missing_critical_info
    return None
