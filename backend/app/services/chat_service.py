from collections.abc import Callable
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from backend.app.agent.classification import classify_risk, classify_scenario
from backend.app.answer_quality.composer import (
    compose_grounded_answer,
    render_grounded_answer_markdown,
)
from backend.app.answer_quality.diagnostics import build_answer_quality_report
from backend.app.answer_quality.models import GroundedAnswerDraft, GroundedAnswerSection
from backend.app.config import Settings, get_settings
from backend.app.core.llm import get_llm_provider
from backend.app.core.providers import LLMMessage
from backend.app.domain.enums import RiskLevel, UserScenario
from backend.app.llm.base import LLMProvider as AdapterLLMProvider
from backend.app.llm.models import (
    LLMMessage as AdapterLLMMessage,
)
from backend.app.llm.models import (
    LLMRequest as AdapterLLMRequest,
)
from backend.app.memory.models import FollowUpContext
from backend.app.memory.service import SessionMemoryService
from backend.app.safety_policy.chat_integration import (
    build_escalation_prefill_from_safety_decision,
    localize_safety_policy_display,
    safety_policy_decision_to_chat_metadata,
    should_recommend_escalation,
)
from backend.app.safety_policy.service import SafetyPolicyService
from backend.app.schemas.chat import ChatRequest, ChatResponse
from backend.app.services.trace_service import TraceService
from backend.app.source_registry.registry import SourceRegistry
from backend.app.source_review_answer_constraints.chat_integration import (
    RUNTIME_SUPPORT_NOTICE,
    classify_source_review_chat_constraint,
    runtime_support_source_ids,
    safe_chat_steps_for_constraint,
    source_review_constraint_to_chat_metadata,
    source_review_warning_for_chat,
)

_DEFAULT_MEMORY_SERVICE = SessionMemoryService()

if TYPE_CHECKING:
    from backend.app.cloud_ai.chat import CloudChatService
    from backend.app.source_conflicts import ConflictResolutionService


class ChatService:
    def __init__(
        self,
        settings: Settings | None = None,
        trace_service: TraceService | None = None,
        use_agent_workflow: bool = False,
        source_registry: SourceRegistry | None = None,
        llm_provider: AdapterLLMProvider | None = None,
        memory_service: SessionMemoryService | None = None,
        safety_policy_service: SafetyPolicyService | None = None,
        cloud_chat_service: "CloudChatService | None" = None,
        case_followup_context: FollowUpContext | None = None,
        profile_followup_context: FollowUpContext | None = None,
        source_conflict_service: "ConflictResolutionService | None" = None,
        semantic_retrieval_service: Any | None = None,
        registry_snapshot: Callable[[], SourceRegistry] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.trace_service = trace_service
        self.use_agent_workflow = use_agent_workflow
        self.source_registry = source_registry
        self.llm_provider = llm_provider
        self.memory_service = memory_service or _DEFAULT_MEMORY_SERVICE
        self.safety_policy_service = safety_policy_service or SafetyPolicyService()
        self.cloud_chat_service = cloud_chat_service
        self.case_followup_context = case_followup_context
        self.profile_followup_context = profile_followup_context
        self.source_conflict_service = source_conflict_service
        self.semantic_retrieval_service = semantic_retrieval_service
        self.registry_snapshot = registry_snapshot
        from backend.app.source_governance.delivery import registry_digests

        self._delivery_source_digests = registry_digests(source_registry)

    def classify_scenario(self, message: str) -> UserScenario:
        return classify_scenario(message)

    def classify_risk(self, message: str, scenario: UserScenario) -> RiskLevel:
        return classify_risk(message, scenario)

    def create_response(self, request: ChatRequest) -> ChatResponse:
        from backend.app.source_governance.delivery import registry_digests

        context = self._build_followup_context(request)
        scenario = self.classify_scenario(request.user_message)
        if scenario == UserScenario.kazakhstan_entry or (
            context is not None and context.active_scenario == UserScenario.kazakhstan_entry.value
        ):
            self.source_registry = self._ensure_kazakhstan_entry_sources(self.source_registry)
            return self._create_kazakhstan_entry_response(
                request,
                context=context,
                source_digests=registry_digests(self.source_registry),
            )

        source_digests = registry_digests(self.source_registry)
        if self.use_agent_workflow:
            return self._create_agent_workflow_response(
                request,
                source_digests=source_digests,
                context=context,
            )

        trace_id = self.trace_service.generate_trace_id() if self.trace_service else str(uuid4())
        if self.trace_service:
            self.trace_service.log_service_start(
                service_name="chat",
                trace_id=trace_id,
                payload={
                    "message_length": len(request.user_message),
                    "has_city": bool(request.city),
                    "preferred_language": request.preferred_language.value,
                },
            )

        risk_level = self.classify_risk(request.user_message, scenario)
        if context is not None:
            scenario = UserScenario(context.active_scenario)
            risk_level = _retain_context_risk(risk_level, context.active_risk_level)
        _llm_text, llm_trace_payload = self._generate_llm_placeholder(request, context)
        escalation_required = risk_level in {
            RiskLevel.emergency,
            RiskLevel.legal_sensitive,
            RiskLevel.work_status_sensitive,
            RiskLevel.medical_sensitive,
        }

        draft = compose_grounded_answer(
            user_message=request.user_message,
            trusted_sources=[],
            scenario=scenario.value,
            risk_level=risk_level.value,
            language=request.preferred_language.value,
        )

        response = ChatResponse(
            trace_id=trace_id,
            session_id=request.session_id,
            scenario=scenario,
            risk_level=risk_level,
            answer=render_grounded_answer_markdown(draft),
            grounded_answer=draft.model_dump(mode="json"),
            metadata={
                "graph_runtime": "local_guidance",
                "used_network": False,
                "used_provider_call": False,
                "followup_context_used": context is not None,
                **llm_trace_payload,
            },
            escalation_required=escalation_required,
            safety_flags=self._safety_flags_for_risk(risk_level),
        )
        self._attach_safety_policy_metadata(
            request,
            response,
            followup_context=context,
            source_digests=source_digests,
        )
        self._remember_local_response(request, response)

        if self.trace_service:
            self.trace_service.log_service_end(
                service_name="chat",
                trace_id=trace_id,
                payload={
                    "message_length": len(request.user_message),
                    "has_city": bool(request.city),
                    "preferred_language": request.preferred_language.value,
                    "scenario": scenario.value,
                    "risk_level": risk_level.value,
                    "escalation_required": escalation_required,
                    "safety_policy_decision": response.safety_policy_decision,
                    "has_source_review_constraints": response.has_source_review_constraints,
                    "source_review_constraint_domain": (
                        response.source_review_constraint or {}
                    ).get("domain"),
                    **llm_trace_payload,
                },
            )

        return response

    @staticmethod
    def _ensure_kazakhstan_entry_sources(
        registry: SourceRegistry | None,
    ) -> SourceRegistry:
        from pathlib import Path

        snapshot = SourceRegistry.from_data_dir(Path("data/sources"))
        entry_sources = [
            source
            for source in snapshot.official_sources()
            if source.source_id.startswith("KZ-MFA-VISA-")
            or source.source_id in {"KZ-EVISA-GUIDE-001", "KZ-ARRIVAL-NOTICE-001"}
            or source.source_id.startswith("KZ-FOREIGNER-")
        ]
        if registry is None:
            return SourceRegistry(entry_sources, [], [])

        existing_ids = {source.source_id for source in registry.all_sources()}
        return SourceRegistry(
            official_sources=[
                *registry.official_sources(),
                *(source for source in entry_sources if source.source_id not in existing_ids),
            ],
            curated_guides=registry.curated_guides(),
            community_posts=registry.retrievable_community_posts(),
        )

    def _generate_llm_placeholder(
        self,
        request: ChatRequest,
        context: FollowUpContext | None = None,
    ) -> tuple[str, dict]:
        from backend.app.memory.context import followup_context_to_prompt_block

        messages = []
        if context is not None:
            messages.append(
                LLMMessage(
                    role="system",
                    content=followup_context_to_prompt_block(context),
                )
            )
        messages.append(LLMMessage(role="user", content=request.user_message))
        if self.llm_provider is not None:
            llm_response = self.llm_provider.generate(
                AdapterLLMRequest(
                    messages=[AdapterLLMMessage(role=m.role, content=m.content) for m in messages]
                )
            )
            return llm_response.content, llm_response.trace_metadata()

        provider = get_llm_provider(self.settings)
        mock_response = provider.generate(messages)
        return mock_response.text, {
            "provider": mock_response.provider,
            "model": mock_response.model,
            "prompt_tokens": mock_response.token_usage.get("prompt_tokens"),
            "completion_tokens": mock_response.token_usage.get("completion_tokens"),
            "total_tokens": mock_response.token_usage.get("total_tokens"),
            "estimated_cost_usd": None,
        }

    def _create_agent_workflow_response(
        self,
        request: ChatRequest,
        *,
        source_digests: dict[str, str],
        context: FollowUpContext | None = None,
    ) -> ChatResponse:
        from backend.app.agent.workflow import DeterministicAgentWorkflow

        continuation = {
            "preferred_language": request.preferred_language,
            "city": request.city or (context.city if context else None),
            "followup_scenario": (
                UserScenario(context.active_scenario)
                if context and context.active_scenario
                else None
            ),
            "followup_risk_level": (
                RiskLevel(context.active_risk_level)
                if context and context.active_risk_level
                else None
            ),
        }
        if self.settings.AGENT_USE_LANGGRAPH:
            from backend.app.agent.langgraph_workflow import (
                langgraph_available,
                run_langgraph_agent,
            )

            if langgraph_available():
                delivered: list[ChatResponse] = []

                def deliver_answer(result):
                    response = _chat_response_from_agent_result(result)
                    self._attach_safety_policy_metadata(
                        request,
                        response,
                        followup_context=context,
                        source_digests=source_digests,
                        **_source_policy_flags_from_agent_result(result),
                    )
                    # Keep graph result/trace aligned with the delivered, checked answer.
                    result.state.final_answer = response.answer
                    result.state.grounded_answer = response.grounded_answer
                    result.state.answer_quality_report = response.answer_quality_report
                    result.state.answer_verification_report = response.answer_verification_report
                    result.state.citations = response.citations
                    result.state.escalation_required = response.escalation_required
                    if response.metadata.get("cloud_status") == "generated":
                        used = {citation.source_id for citation in response.citations}
                        result.state.selected_sources = [
                            source
                            for source in result.state.selected_sources
                            if source.source.source_id in used
                        ]
                    if response.has_source_review_constraints or response.metadata.get(
                        "source_publication_gate", {}
                    ).get("claims_withheld"):
                        result.state.selected_sources = []
                        result.state.citations = []
                    result.state.safety_flags = response.safety_flags
                    delivered.append(response)
                    return response.metadata

                result = run_langgraph_agent(
                    user_message=request.user_message,
                    user_id=request.user_id,
                    session_id=request.session_id,
                    source_registry=self.source_registry,
                    use_hybrid_rag=self.settings.AGENT_LANGGRAPH_USE_HYBRID_RAG,
                    trace_service=self.trace_service,
                    semantic_retrieval_service=self.semantic_retrieval_service,
                    answer_delivery=deliver_answer,
                    **continuation,
                )
                response = delivered[0]
                response.metadata.update(result.metadata)
                self._remember_agent_result(request, result, response)
                return response

            result = DeterministicAgentWorkflow(
                source_registry=self.source_registry,
                trace_service=self.trace_service,
                semantic_retrieval_service=self.semantic_retrieval_service,
            ).run(
                user_message=request.user_message,
                user_id=request.user_id,
                session_id=request.session_id,
                **continuation,
            )
            result.safety_flags.append("langgraph_unavailable_deterministic_fallback")
            response = _chat_response_from_agent_result(result)
            self._attach_safety_policy_metadata(
                request,
                response,
                followup_context=context,
                source_digests=source_digests,
                **_source_policy_flags_from_agent_result(result),
            )
            self._remember_agent_result(request, result, response)
            return response

        result = DeterministicAgentWorkflow(
            source_registry=self.source_registry,
            trace_service=self.trace_service,
            semantic_retrieval_service=self.semantic_retrieval_service,
        ).run(
            user_message=request.user_message,
            user_id=request.user_id,
            session_id=request.session_id,
            **continuation,
        )

        response = _chat_response_from_agent_result(result)
        self._attach_safety_policy_metadata(
            request,
            response,
            followup_context=context,
            source_digests=source_digests,
            **_source_policy_flags_from_agent_result(result),
        )
        self._remember_agent_result(request, result, response)
        return response

    def _create_kazakhstan_entry_response(
        self,
        request: ChatRequest,
        *,
        context: FollowUpContext | None,
        source_digests: dict[str, str],
    ) -> ChatResponse:
        from backend.app.kazakhstan_entry import (
            build_kazakhstan_entry_answer,
            render_kazakhstan_entry_answer,
        )
        from backend.app.kazakhstan_foreign_services import (
            build_kazakhstan_foreigner_service_answer,
            render_kazakhstan_foreigner_service_answer,
        )

        trace_id = self.trace_service.generate_trace_id() if self.trace_service else str(uuid4())
        if self.trace_service:
            self.trace_service.log_service_start(
                service_name="chat",
                trace_id=trace_id,
                payload={
                    "message_length": len(request.user_message),
                    "has_city": bool(request.city),
                    "preferred_language": request.preferred_language.value,
                    "scenario": UserScenario.kazakhstan_entry.value,
                    "answer_mode": "official_foreigner_service_or_visa_lookup",
                },
            )

        context_text = "\n".join(
            f"{turn.role}: {turn.text}" for turn in (context.recent_messages if context else [])
        )
        service_answer = build_kazakhstan_foreigner_service_answer(
            request.user_message,
            request.preferred_language,
            self.source_registry,
            context_text=context_text,
        )
        visa_answer = None
        service_intent = service_answer[2].get("intent") if service_answer is not None else None
        if service_intent in {"tourism", "consular_documents_tourist_evisa"}:
            visa_answer = build_kazakhstan_entry_answer(
                request.user_message,
                request.preferred_language,
                self.source_registry,
                context_text=context_text,
            )
            visa_draft, visa_citations, visa_lookup = visa_answer
            if visa_lookup.get("country") and any(
                citation.source_id.startswith("KZ-MFA-VISA-") for citation in visa_citations
            ):
                if service_intent == "tourism":
                    service_answer = None
                else:
                    service_draft, service_citations, service_lookup = service_answer
                    service_draft.direct_answer = (
                        f"{visa_draft.direct_answer}\n\n{service_draft.direct_answer}"
                    )
                    service_draft.grounded_facts = [
                        *visa_draft.grounded_facts,
                        *service_draft.grounded_facts,
                    ]
                    service_draft.recommended_steps = [
                        *visa_draft.recommended_steps,
                        *service_draft.recommended_steps,
                    ]
                    service_draft.uncertainty = list(
                        dict.fromkeys(
                            [
                                *visa_draft.uncertainty,
                                *service_draft.uncertainty,
                            ]
                        )
                    )
                    service_draft.source_notes = [
                        *visa_draft.source_notes,
                        *service_draft.source_notes,
                    ]
                    merged_source_ids = list(
                        dict.fromkeys(
                            source_id
                            for source_id in (
                                *(visa_lookup.get("source_ids") or "").split(","),
                                *(service_lookup.get("source_ids") or "").split(","),
                            )
                            if source_id
                        )
                    )
                    service_answer = (
                        service_draft,
                        [*visa_citations, *service_citations],
                        {
                            **service_lookup,
                            "intent": "consular_documents_tourist_evisa_with_visa_regime",
                            "source_ids": ",".join(merged_source_ids),
                        },
                    )
        if service_answer is not None:
            draft, citations, lookup = service_answer
            render_answer = render_kazakhstan_foreigner_service_answer
        else:
            draft, citations, lookup = visa_answer or build_kazakhstan_entry_answer(
                request.user_message,
                request.preferred_language,
                self.source_registry,
                context_text=context_text,
            )
            render_answer = render_kazakhstan_entry_answer
        risk_level = self.classify_risk(request.user_message, UserScenario.kazakhstan_entry)
        if context is not None:
            risk_level = _retain_context_risk(risk_level, context.active_risk_level)
        draft.risk_level = risk_level.value
        trace_source_ids = [citation.source_id for citation in citations]

        def current_entry_snapshot() -> SourceRegistry:
            current = self.registry_snapshot() if self.registry_snapshot else self.source_registry
            return self._ensure_kazakhstan_entry_sources(current)

        response = ChatResponse(
            trace_id=trace_id,
            session_id=request.session_id,
            scenario=UserScenario.kazakhstan_entry,
            risk_level=risk_level,
            answer=render_answer(draft),
            citations=citations,
            grounded_answer=draft.model_dump(mode="json"),
            answer_quality_report=build_answer_quality_report(draft).model_dump(mode="json"),
            answer_verification_report={
                "passed": bool(citations),
                "scope": (
                    "deterministic_official_foreigner_service_lookup"
                    if lookup.get("intent")
                    else "deterministic_official_visa_table_lookup"
                ),
                "supported_claim_count": len(citations),
                "unsupported_claim_count": 0,
            },
            metadata={
                "graph_runtime": (
                    "deterministic_official_foreigner_service_lookup"
                    if lookup.get("intent")
                    else "deterministic_official_table_lookup"
                ),
                "used_network": False,
                "used_provider_call": False,
                "followup_context_used": context is not None,
                "kazakhstan_entry_official_lookup": True,
                "kazakhstan_entry_lookup": lookup,
                "selected_source_ids": list(dict.fromkeys(trace_source_ids)),
            },
            escalation_required=risk_level
            in {
                RiskLevel.emergency,
                RiskLevel.legal_sensitive,
                RiskLevel.work_status_sensitive,
                RiskLevel.medical_sensitive,
            },
            safety_flags=self._safety_flags_for_risk(risk_level),
        )
        self._attach_safety_policy_metadata(
            request,
            response,
            has_official_source=bool(citations),
            followup_context=context,
            source_digests=source_digests,
            source_registry_snapshot=current_entry_snapshot,
            skip_cloud_enrichment=True,
        )
        self._remember_local_response(request, response)

        if self.trace_service:
            self.trace_service.log_service_end(
                service_name="chat",
                trace_id=trace_id,
                payload={
                    "message_length": len(request.user_message),
                    "has_city": bool(request.city),
                    "preferred_language": request.preferred_language.value,
                    "scenario": UserScenario.kazakhstan_entry.value,
                    "risk_level": response.risk_level.value,
                    "escalation_required": response.escalation_required,
                    "has_official_source": bool(citations),
                    "source_ids": list(dict.fromkeys(trace_source_ids)),
                    "has_source_review_constraints": response.has_source_review_constraints,
                },
            )
        return response

    def _build_followup_context(self, request: ChatRequest) -> FollowUpContext | None:
        if not request.session_id:
            return None
        if request.reset_context:
            self.memory_service.clear_session(request.session_id)
        if request.use_saved_context is False:
            return (
                self._session_followup_context(request)
                if request.use_conversation_context
                else None
            )
        # A saved case owns its conversation; a client session cannot inject another history.
        if self.case_followup_context is not None:
            return self.case_followup_context
        profile = self.profile_followup_context
        context = None if request.reset_context else self._session_followup_context(request)
        if profile is not None:
            if context is not None:
                context = context.model_copy(deep=True)
                context.city = profile.city
                context.task_context = profile.task_context.copy()
                context.warnings += profile.warnings
                return context
            return profile
        return context

    def _session_followup_context(self, request: ChatRequest) -> FollowUpContext | None:
        context = self.memory_service.build_context(request.session_id)
        if not context.active_scenario or context.active_scenario == "unclear":
            if request.use_conversation_context and context.recent_messages:
                return context
            return None
        current = self.classify_scenario(request.user_message)
        normalized = request.user_message.casefold()
        # Memory selects the ongoing task only. Sources are always retrieved afresh.
        generic_document_followup = current == UserScenario.documents and any(
            term in normalized
            for term in (
                "what documents",
                "which documents",
                "какие документы",
                "какие бумаги",
                "қандай құжат",
                "什么材料",
                "哪些材料",
                "什么文件",
            )
        )
        if current not in {UserScenario.unclear, UserScenario(context.active_scenario)}:
            if not generic_document_followup:
                if request.use_conversation_context:
                    return context.model_copy(
                        update={
                            "active_scenario": current.value,
                            "active_risk_level": self.classify_risk(
                                request.user_message,
                                current,
                            ).value,
                        }
                    )
                return None
        return context

    def _remember_local_response(
        self,
        request: ChatRequest,
        response: ChatResponse,
    ) -> None:
        if not request.session_id:
            return
        self.memory_service.add_turn(
            session_id=request.session_id,
            role="user",
            text=request.user_message,
            scenario=response.scenario.value,
            risk_level=response.risk_level.value,
            language=request.preferred_language.value,
            metadata={"city": request.city or ""},
        )
        self.memory_service.add_turn(
            session_id=request.session_id,
            role="assistant",
            text=response.answer,
            scenario=response.scenario.value,
            risk_level=response.risk_level.value,
            language=request.preferred_language.value,
            metadata={
                "trace_id": response.trace_id,
                **(
                    {"assistant_mode": response.metadata["assistant_mode"]}
                    if response.metadata.get("assistant_mode")
                    in {"dialogue", "translation", "document_qa"}
                    else {}
                ),
                **(
                    {"active_writing_request": response.metadata["active_writing_request"]}
                    if response.metadata.get("assistant_mode") == "dialogue"
                    and isinstance(response.metadata.get("active_writing_request"), bool)
                    else {}
                ),
            },
        )

    def _remember_agent_result(self, request: ChatRequest, result, response: ChatResponse) -> None:
        if not request.session_id:
            return
        # Persist the delivered answer, including post-composition safety constraints.
        result = result.model_copy(deep=True)
        result.answer = response.answer
        result.escalation_required = response.escalation_required
        result.state.final_answer = response.answer
        result.state.grounded_answer = response.grounded_answer
        result.state.answer_quality_report = response.answer_quality_report
        result.state.answer_verification_report = response.answer_verification_report
        if response.metadata.get("cloud_status") == "generated":
            result.selected_source_ids = list(
                dict.fromkeys(c.source_id for c in response.citations)
            )
            result.state.hybrid_rag_result = None
            result.state.checklist = None
            result.citations = response.citations
            notes = (response.grounded_answer or {}).get("source_notes", [])
            result.metadata.update(
                hybrid_rag_evidence_count=len(notes),
                official_count=sum(n.get("source_type") == "official" for n in notes),
                curated_count=sum(n.get("source_type") == "curated_guide" for n in notes),
                community_count=0,
                has_official_or_curated=bool(notes),
            )
            result.state.selected_sources = [
                s
                for s in result.state.selected_sources
                if s.source.source_id in result.selected_source_ids
            ]
        if response.has_source_review_constraints or response.metadata.get(
            "source_publication_gate", {}
        ).get("claims_withheld"):
            result.state.selected_sources = []
            result.state.hybrid_rag_result = None
            result.state.checklist = None
            result.citations = []
            result.selected_source_ids = []
            result.metadata = {
                **result.metadata,
                "hybrid_rag_evidence_count": 0,
                "official_count": 0,
                "curated_count": 0,
                "community_count": 0,
                "has_official_or_curated": False,
            }
        assistant_mode = response.metadata.get("assistant_mode")
        if assistant_mode in {"dialogue", "translation", "document_qa"}:
            result.metadata["assistant_mode"] = assistant_mode
        active_writing_request = response.metadata.get("active_writing_request")
        if assistant_mode == "dialogue" and isinstance(active_writing_request, bool):
            result.metadata["active_writing_request"] = active_writing_request
        self.memory_service.update_from_agent_result(
            request.session_id,
            result,
            user_message=request.user_message,
        )
        if request.city:
            self.memory_service.set_city(request.session_id, request.city, only_if_empty=True)

    def _attach_safety_policy_metadata(
        self,
        request: ChatRequest,
        response: ChatResponse,
        *,
        has_official_source: bool = False,
        has_curated_source: bool = False,
        has_unreviewed_sources: bool = False,
        followup_context: FollowUpContext | None = None,
        source_digests: dict[str, str] | None = None,
        source_registry_snapshot: Callable[[], SourceRegistry] | None = None,
        skip_cloud_enrichment: bool = False,
    ) -> None:
        original_registry = self.source_registry
        conflict_evaluation = None
        conflict_failed = False
        detected_ids: list[str] = []
        if self.source_conflict_service is not None and original_registry is not None:
            from backend.app.source_conflicts import ConflictIntegrityError
            from backend.app.source_conflicts.delivery import (
                detected_conflict_ids,
                filtered_registry,
                preferred_quotes,
                recompose_selected,
                response_source_ids,
            )
            from backend.app.source_conflicts.registry import full_registry_sources

            try:
                conflict_evaluation = self.source_conflict_service.evaluate(
                    sources=full_registry_sources(original_registry),
                    selected_source_ids=response_source_ids(response),
                    scenario=response.scenario,
                    risk_level=response.risk_level,
                    city=request.city or (followup_context.city if followup_context else None),
                    applicability=request.source_applicability,
                )
                if conflict_evaluation.excluded_source_ids:
                    recompose_selected(
                        request,
                        response,
                        original_registry,
                        conflict_evaluation.excluded_source_ids,
                        preferred=[
                            sid
                            for item in conflict_evaluation.applied
                            for sid in item.preferred_source_ids
                        ],
                        quotes=preferred_quotes(conflict_evaluation),
                    )
                    self.source_registry = filtered_registry(
                        original_registry,
                        conflict_evaluation.excluded_source_ids,
                    )
                detected_ids = detected_conflict_ids(response, self.source_registry)
            except ConflictIntegrityError:
                conflict_failed = True
        blocked = (
            conflict_failed
            or bool(detected_ids)
            or bool(conflict_evaluation and conflict_evaluation.blocked_conflict_ids)
        )
        if blocked and self.cloud_chat_service is not None:
            response.metadata["cloud_status"] = "source_conflict_requires_review"
        if self.cloud_chat_service is not None and not blocked and not skip_cloud_enrichment:
            self.cloud_chat_service.enrich(
                request,
                response,
                self.source_registry,
                context=followup_context,
            )
            if self.trace_service:
                self.trace_service.log_event(
                    event_type="cloud_answer",
                    trace_id=response.trace_id,
                    payload={
                        key: response.metadata.get(key)
                        for key in (
                            "cloud_status",
                            "provider",
                            "model",
                            "used_network",
                            "used_provider_call",
                            "total_tokens",
                            "assistant_mode",
                            "language_tool",
                        )
                    },
                )
        decision = self.safety_policy_service.evaluate(
            query=request.user_message,
            scenario=response.scenario.value,
            risk_level=response.risk_level.value,
            has_official_source=has_official_source,
            has_curated_source=has_curated_source,
            has_unreviewed_sources=has_unreviewed_sources,
        )
        response.safety_policy_decision = safety_policy_decision_to_chat_metadata(decision)
        response.high_risk = decision.high_risk
        response.requires_official_source = decision.requires_official_source
        response.requires_human_escalation = decision.requires_human_escalation
        response.requires_emergency_authority = decision.requires_emergency_authority
        response.not_emergency_dispatch = decision.not_emergency_dispatch
        response.required_warnings, response.recommended_next_steps = (
            localize_safety_policy_display(
                decision.required_warnings,
                decision.recommended_next_steps,
                request.preferred_language.value,
            )
        )
        response.escalation_recommended = should_recommend_escalation(decision)
        response.escalation_required = (
            response.escalation_required
            or decision.requires_human_escalation
            or decision.requires_emergency_authority
        )
        if response.escalation_recommended:
            response.escalation_prefill = build_escalation_prefill_from_safety_decision(
                decision,
                request.user_message,
                scenario=response.scenario.value,
                risk_level=response.risk_level.value,
                session_id=request.session_id,
                user_id=request.user_id,
            )
        response.safety_flags = _unique_strings(
            response.safety_flags + _safety_flags_from_policy(decision)
        )
        self._attach_source_review_constraint_metadata(
            request,
            response,
            city=request.city or (followup_context.city if followup_context else None),
        )
        self.source_registry = original_registry
        self._apply_source_conflict_delivery_gate(
            request,
            response,
            original_registry,
            conflict_evaluation,
            conflict_failed=conflict_failed,
            followup_context=followup_context,
            detected_ids=detected_ids,
        )
        from backend.app.source_governance.delivery import apply_source_delivery_gate

        apply_source_delivery_gate(
            request,
            response,
            original_registry,
            initial_digests=(
                source_digests if source_digests is not None else self._delivery_source_digests
            ),
            registry_snapshot=(source_registry_snapshot or self.registry_snapshot),
            city=request.city or (followup_context.city if followup_context else None),
        )
        runtime_support = response.metadata.get("source_review_runtime_support")
        if runtime_support is not None:
            admitted = (
                response.metadata.get("source_publication_gate", {}).get("status") == "passed"
            )
            runtime_support["status"] = "verified_scoped_facts" if admitted else "withheld"
            if not admitted and response.metadata.get("cloud_status") == "generated":
                response.metadata["cloud_status"] = "source_publication_withheld"

        if response.metadata.get("inference_backend") == "ollama":
            status = response.metadata.get("cloud_status")
            if response.metadata.get("source_resolution", {}).get("claims_withheld"):
                status = "source_conflict_withheld"
            if response.metadata.get("source_publication_gate", {}).get("claims_withheld"):
                status = "source_publication_withheld"
            response.metadata["ollama_status"] = status
            if self.trace_service:
                self.trace_service.log_event(
                    event_type="local_answer_delivery",
                    trace_id=response.trace_id,
                    payload={
                        "ollama_status": status,
                        "local_generation_completed": response.metadata.get(
                            "local_generation_completed", False
                        ),
                    },
                )

    def _apply_source_conflict_delivery_gate(
        self,
        request: ChatRequest,
        response: ChatResponse,
        registry: SourceRegistry | None,
        prior_evaluation,
        *,
        conflict_failed: bool,
        followup_context: FollowUpContext | None,
        detected_ids: list[str],
    ) -> None:
        if self.source_conflict_service is None or registry is None:
            return
        from backend.app.source_conflicts import ConflictIntegrityError, ConflictRevisionError
        from backend.app.source_conflicts.delivery import (
            attach_reviewed_notes,
            detected_conflict_ids,
            filtered_registry,
            response_source_ids,
            verify_reviewed_answer,
            withhold_conflicting_claims,
        )
        from backend.app.source_conflicts.registry import full_registry_sources

        blocked_ids = list(
            dict.fromkeys(
                [
                    *detected_ids,
                    *(prior_evaluation.blocked_conflict_ids if prior_evaluation else []),
                ]
            )
        )
        try:
            evaluation = self.source_conflict_service.evaluate(
                sources=full_registry_sources(registry),
                selected_source_ids=response_source_ids(response),
                scenario=response.scenario,
                risk_level=response.risk_level,
                city=request.city or (followup_context.city if followup_context else None),
                applicability=request.source_applicability,
            )
            blocked_ids = list(dict.fromkeys([*blocked_ids, *evaluation.blocked_conflict_ids]))
            if set(response_source_ids(response)).intersection(evaluation.excluded_source_ids):
                blocked_ids.append("source_resolution_not_followed")
            blocked_ids = list(
                dict.fromkeys(
                    [
                        *blocked_ids,
                        *detected_conflict_ids(
                            response,
                            filtered_registry(registry, evaluation.excluded_source_ids),
                        ),
                    ]
                )
            )
            if conflict_failed or blocked_ids:
                withhold_conflicting_claims(request, response, blocked_ids)
            elif evaluation.applied and response_source_ids(response):
                attach_reviewed_notes(response, evaluation)
                if verify_reviewed_answer(request, response, registry, evaluation):
                    self.source_conflict_service.record_usage(response.trace_id, evaluation)
                else:
                    withhold_conflicting_claims(
                        request,
                        response,
                        [item.conflict_id for item in evaluation.applied],
                    )
        except (ConflictIntegrityError, ConflictRevisionError):
            withhold_conflicting_claims(request, response, blocked_ids)
        if response.metadata.get("source_resolution") and self.trace_service:
            self.trace_service.log_event(
                event_type="source_resolution",
                trace_id=response.trace_id,
                payload=response.metadata["source_resolution"],
            )

    def _attach_source_review_constraint_metadata(
        self,
        request: ChatRequest,
        response: ChatResponse,
        *,
        city: str | None = None,
    ) -> None:
        if response.metadata.get("kazakhstan_entry_official_lookup"):
            response.has_source_review_constraints = False
            response.source_review_constraint = None
            response.prohibited_claim_types = []
            response.citizen_visible_source_review_disclosure_allowed = False
            if response.citations:
                response.requires_official_source = True
                response.metadata["source_review_runtime_support"] = {
                    "status": "pending_final_publication_check",
                    "domain": "kazakhstan_entry_visa",
                    "source_ids": list(
                        dict.fromkeys(citation.source_id for citation in response.citations)
                    ),
                    "scope": "automated_exact_row_lookup_and_cited_official_guidance",
                    "complete_procedure_verified": False,
                }
            return
        if response.metadata.get("assistant_mode") in {"dialogue", "translation", "document_qa"}:
            response.has_source_review_constraints = False
            return
        constraint = classify_source_review_chat_constraint(
            request.user_message,
            scenario=response.scenario.value,
        )
        if constraint is None:
            response.has_source_review_constraints = False
            return

        supported_ids = runtime_support_source_ids(
            response,
            self.source_registry,
            domain=constraint.domain,
            city=city,
            user_message=request.user_message,
        )
        if supported_ids:
            language = request.preferred_language.value
            notice = RUNTIME_SUPPORT_NOTICE.get(language, RUNTIME_SUPPORT_NOTICE["en"])
            draft = GroundedAnswerDraft.model_validate(response.grounded_answer)
            draft.uncertainty = _unique_strings([*draft.uncertainty, notice])
            response.grounded_answer = draft.model_dump(mode="json")
            response.answer = render_grounded_answer_markdown(draft)
            response.answer_quality_report = build_answer_quality_report(draft).model_dump(
                mode="json",
            )
            response.has_source_review_constraints = False
            response.required_official_verification_warning = notice
            response.requires_official_source = True
            response.required_warnings = _unique_strings([*response.required_warnings, notice])
            response.metadata["source_review_runtime_support"] = {
                "status": "pending_final_publication_check",
                "domain": constraint.domain,
                "source_ids": supported_ids,
                "scope": "delivered_citation_backed_facts_only",
                "complete_procedure_verified": False,
            }
            return

        language = request.preferred_language.value
        warning = source_review_warning_for_chat(constraint, language)
        steps = safe_chat_steps_for_constraint(constraint, language)
        response.has_source_review_constraints = True
        if response.metadata.get("cloud_status") == "generated":
            response.metadata["cloud_status"] = "source_constraints_applied"
        response.source_review_constraint = source_review_constraint_to_chat_metadata(constraint)
        response.required_official_verification_warning = warning
        response.prohibited_claim_types = list(constraint.prohibited_claim_types)
        response.citizen_visible_source_review_disclosure_allowed = False
        safe_draft = compose_grounded_answer(
            user_message=request.user_message,
            trusted_sources=[],
            scenario=response.scenario.value,
            risk_level=response.risk_level.value,
            language=language,
        )
        if response.risk_level in {
            RiskLevel.emergency,
            RiskLevel.unsafe,
            RiskLevel.prompt_injection,
        }:
            # Official-source gaps must never replace urgent help or a safety refusal.
            if response.grounded_answer:
                safe_draft = GroundedAnswerDraft.model_validate(response.grounded_answer)
            safe_draft.uncertainty = _unique_strings(safe_draft.uncertainty + [warning])
        else:
            safe_draft.direct_answer = warning
            safe_draft.recommended_steps = [
                GroundedAnswerSection(heading="", body=step) for step in steps
            ]
        safe_draft.grounded_facts = []
        safe_draft.source_notes = []
        response.grounded_answer = safe_draft.model_dump(mode="json")
        response.answer_quality_report = build_answer_quality_report(safe_draft).model_dump(
            mode="json"
        )
        response.answer = render_grounded_answer_markdown(safe_draft)
        response.citations = []
        response.required_warnings = _unique_strings(response.required_warnings + [warning])
        response.recommended_next_steps = _unique_strings(response.recommended_next_steps + steps)
        response.requires_official_source = True
        response.safety_flags = _unique_strings(
            response.safety_flags
            + [
                "source_review_constraint_applied",
                f"source_review_constraint_{constraint.domain}",
            ]
        )

    @staticmethod
    def _safety_flags_for_risk(risk_level: RiskLevel) -> list[str]:
        if risk_level == RiskLevel.emergency:
            return ["human_or_official_escalation_recommended"]
        if risk_level == RiskLevel.work_status_sensitive:
            return ["work_status_sensitive"]
        if risk_level == RiskLevel.medical_sensitive:
            return ["medical_sensitive"]
        if risk_level == RiskLevel.legal_sensitive:
            return ["legal_sensitive"]
        return []


def _chat_response_from_agent_result(result) -> ChatResponse:
    return ChatResponse(
        trace_id=result.trace_id,
        session_id=result.state.session_id,
        scenario=result.scenario,
        risk_level=result.risk_level,
        answer=result.answer,
        citations=result.citations,
        escalation_required=result.escalation_required,
        safety_flags=result.safety_flags,
        grounded_answer=result.state.grounded_answer,
        answer_quality_report=result.state.answer_quality_report,
        answer_verification_report=result.state.answer_verification_report,
        metadata={
            **result.metadata,
            "contains_synthetic_sources": any(
                note.get("is_synthetic", False)
                for note in (result.state.grounded_answer or {}).get("source_notes", [])
            ),
        },
    )


def _source_policy_flags_from_agent_result(result) -> dict[str, bool]:
    selected_sources = getattr(result.state, "selected_sources", [])
    has_official_source = any(
        getattr(source.source.source_type, "value", source.source.source_type) == "official"
        for source in selected_sources
    )
    has_curated_source = any(
        getattr(source.source.source_type, "value", source.source.source_type) == "curated_guide"
        for source in selected_sources
    )
    return {
        "has_official_source": has_official_source,
        "has_curated_source": has_curated_source,
        "has_unreviewed_sources": (
            getattr(result.state, "unreviewed_source_candidate_count", 0) > 0
        ),
    }


def _safety_flags_from_policy(decision) -> list[str]:
    flags = ["safety_policy_evaluated"]
    if decision.requires_official_source:
        flags.append("safety_policy_official_source_required")
    if decision.requires_human_escalation:
        flags.append("safety_policy_human_escalation_required")
    if decision.requires_emergency_authority:
        flags.append("safety_policy_emergency_authority_required")
    if decision.not_emergency_dispatch:
        flags.append("not_emergency_dispatch")
    return flags


def _unique_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _retain_context_risk(current: RiskLevel, previous: str | None) -> RiskLevel:
    if current in {RiskLevel.unsafe, RiskLevel.prompt_injection, RiskLevel.emergency}:
        return current
    if previous in {"emergency", "legal_sensitive", "medical_sensitive", "work_status_sensitive"}:
        return RiskLevel(previous)
    return current
