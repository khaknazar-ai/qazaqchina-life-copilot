from collections.abc import Callable
from pathlib import Path
from typing import Any, NotRequired, TypedDict
from uuid import uuid4

from backend.app.agent.nodes import (
    citation_stub_node,
    escalation_decider_node,
    final_response_node,
    grounded_answer_quality_node,
    input_guard_node,
    language_detector_node,
    profile_extraction_node,
    retrieval_node,
    retrieval_planner_node,
    risk_classifier_node,
    scenario_router_node,
    source_governance_node,
)
from backend.app.agent.result import AgentWorkflowResult
from backend.app.agent.runtime_tools import AgentToolPlan, execute_tools, plan_tools
from backend.app.answer_quality.composer import (
    render_grounded_answer_markdown,
)
from backend.app.answer_quality.diagnostics import build_answer_quality_report
from backend.app.answer_quality.localization import copy
from backend.app.answer_quality.models import GroundedAnswerDraft
from backend.app.answer_quality.policies import build_source_note
from backend.app.domain.agent import AgentState
from backend.app.domain.enums import LanguageCode, RiskLevel, UserScenario
from backend.app.domain.sources import Citation, RetrievedSource
from backend.app.rag.engine import HybridRAGEngine
from backend.app.rag.models import HybridRAGResult
from backend.app.retrieval.planner import RetrievalPlanningInput
from backend.app.retrieval.quality import (
    RetrievalQualityInput,
    build_retrieval_quality_report,
)
from backend.app.retrieval.service import RetrievalService
from backend.app.services.trace_service import TraceService
from backend.app.source_registry.registry import SourceRegistry
from backend.app.verification.gate import verify_agent_answer

try:
    from langgraph.graph import END, START, StateGraph
except ImportError:  # pragma: no cover - exercised when dependency is absent
    END = None
    START = None
    StateGraph = None


GRAPH_NODE_SEQUENCE = [
    "classify_or_plan",
    "retrieve_trusted_sources",
    "evaluate_source_coverage",
    "controlled_tool_decision",
    "execute_agent_tools",
    "compose_grounded_answer",
    "verify_safety",
    "finalize_response",
    "generate_and_verify_answer",
]


class LangGraphAgentState(TypedDict):
    agent_state: AgentState
    graph_nodes_executed: list[str]
    scenario_hint: NotRequired[str | None]
    risk_level_hint: NotRequired[str | None]
    language_hint: NotRequired[str | None]
    retrieval_plan: NotRequired[Any]
    retrieval_quality_report: NotRequired[Any]
    hybrid_rag_result: NotRequired[HybridRAGResult | None]
    retrieval_runtime: NotRequired[str]
    use_hybrid_rag: NotRequired[bool]
    graph_metadata: NotRequired[dict[str, Any]]
    tool_plan: NotRequired[AgentToolPlan]
    delivery_metadata: NotRequired[dict[str, Any]]


def langgraph_available() -> bool:
    return StateGraph is not None and START is not None and END is not None


def graph_node_names() -> list[str]:
    return list(GRAPH_NODE_SEQUENCE)


def build_langgraph_agent(
    source_registry: SourceRegistry | None = None,
    retrieval_service: RetrievalService | None = None,
    use_hybrid_rag: bool = True,
    semantic_retrieval_service: Any | None = None,
    answer_delivery: Callable[[AgentWorkflowResult], dict[str, Any]] | None = None,
):
    if not langgraph_available():
        raise RuntimeError("LangGraph is not installed. Install the 'langgraph' dependency.")

    registry = source_registry or SourceRegistry.from_data_dir(Path("data/sources"))
    service = retrieval_service or RetrievalService(source_registry=registry)

    graph = StateGraph(LangGraphAgentState)
    graph.add_node("classify_or_plan", _classify_or_plan_node(service))
    graph.add_node(
        "retrieve_trusted_sources",
        _retrieve_trusted_sources_node(
            retrieval_service=service,
            source_registry=registry,
            use_hybrid_rag=use_hybrid_rag,
            semantic_retrieval_service=semantic_retrieval_service,
        ),
    )
    graph.add_node("evaluate_source_coverage", _evaluate_source_coverage_node())
    graph.add_node("controlled_tool_decision", _controlled_tool_decision_node())
    graph.add_node("execute_agent_tools", _execute_agent_tools_node)
    graph.add_node("compose_grounded_answer", _compose_grounded_answer_node())
    graph.add_node("verify_safety", _verify_safety_node())
    graph.add_node("finalize_response", _finalize_response_node())
    graph.add_node("generate_and_verify_answer", _delivery_node(answer_delivery))

    graph.add_edge(START, "classify_or_plan")
    for source_node, target_node in zip(GRAPH_NODE_SEQUENCE, GRAPH_NODE_SEQUENCE[1:]):
        if source_node == "controlled_tool_decision":
            continue
        graph.add_edge(source_node, target_node)
    graph.add_conditional_edges(
        "controlled_tool_decision",
        lambda state: (
            "execute_agent_tools" if state["tool_plan"].names else "compose_grounded_answer"
        ),
        ["execute_agent_tools", "compose_grounded_answer"],
    )
    graph.add_edge("generate_and_verify_answer", END)
    return graph.compile()


def run_langgraph_agent(
    user_message: str,
    scenario: str | None = None,
    risk_level: str | None = None,
    language: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    source_registry: SourceRegistry | None = None,
    retrieval_service: RetrievalService | None = None,
    use_hybrid_rag: bool = True,
    preferred_language: LanguageCode | None = None,
    city: str | None = None,
    followup_scenario: UserScenario | None = None,
    followup_risk_level: RiskLevel | None = None,
    trace_service: TraceService | None = None,
    semantic_retrieval_service: Any | None = None,
    answer_delivery: Callable[[AgentWorkflowResult], dict[str, Any]] | None = None,
) -> AgentWorkflowResult:
    if not langgraph_available():
        raise RuntimeError("LangGraph is not installed. Install the 'langgraph' dependency.")

    initial_state: LangGraphAgentState = {
        "agent_state": _initial_agent_state(
            user_message=user_message,
            language=preferred_language or language,
            user_id=user_id,
            session_id=session_id,
            city=city,
            followup_scenario=followup_scenario,
            followup_risk_level=followup_risk_level,
        ),
        "graph_nodes_executed": [],
        "scenario_hint": scenario,
        "risk_level_hint": risk_level,
        "language_hint": preferred_language or language,
        "use_hybrid_rag": use_hybrid_rag,
    }
    graph = build_langgraph_agent(
        source_registry=source_registry,
        retrieval_service=retrieval_service,
        use_hybrid_rag=use_hybrid_rag,
        semantic_retrieval_service=semantic_retrieval_service,
        answer_delivery=answer_delivery,
    )
    output = initial_state
    trace_id = initial_state["agent_state"].trace_id
    if trace_service:
        trace_service.log_event(
            event_type="workflow_start",
            trace_id=trace_id,
            payload={"graph_runtime": "langgraph", "message_length": len(user_message)},
        )
    for update in _stream_with_error_trace(graph, initial_state, trace_service):
        for node_name, node_output in update.items():
            output = {**output, **node_output}
            if trace_service:
                node_state = output["agent_state"]
                trace_service.log_event(
                    event_type="node_end",
                    trace_id=trace_id,
                    payload={
                        "node_name": node_name,
                        "scenario": node_state.scenario.value,
                        "risk_level": node_state.risk_level.value,
                        "selected_source_count": len(node_state.selected_sources),
                        "tool_trace": node_state.tool_trace
                        if node_name == "execute_agent_tools"
                        else None,
                    },
                )
    state = output["agent_state"]
    node_sequence = output.get("graph_nodes_executed", [])
    metadata = _graph_metadata(output)
    if trace_service:
        trace_service.log_event(
            event_type="workflow_end",
            trace_id=trace_id,
            payload={
                "graph_runtime": "langgraph",
                "node_count": len(node_sequence),
                "scenario": state.scenario.value,
                "risk_level": state.risk_level.value,
                "escalation_required": state.escalation_required,
                "answer_verification_passed": metadata["answer_verification_passed"],
            },
        )
    return _result_from_graph(output)


def _stream_with_error_trace(graph, initial_state, trace_service):
    try:
        yield from graph.stream(initial_state, stream_mode="updates")
    except Exception as exc:
        if trace_service:
            trace_service.log_event(
                event_type="workflow_error",
                trace_id=initial_state["agent_state"].trace_id,
                payload={"graph_runtime": "langgraph", "error_code": type(exc).__name__},
            )
        raise


def _result_from_graph(output: LangGraphAgentState) -> AgentWorkflowResult:
    state = output["agent_state"]
    return AgentWorkflowResult(
        state=state,
        answer=state.final_answer or "",
        trace_id=state.trace_id,
        scenario=state.scenario,
        risk_level=state.risk_level,
        escalation_required=state.escalation_required,
        citations=state.citations,
        selected_source_ids=_unique_source_ids(state),
        node_sequence=output.get("graph_nodes_executed", []),
        safety_flags=state.safety_flags,
        metadata=_graph_metadata(output),
    )


def _classify_or_plan_node(retrieval_service: RetrievalService):
    def node(graph_state: LangGraphAgentState) -> LangGraphAgentState:
        state = graph_state["agent_state"]
        state = input_guard_node(state)
        state = language_detector_node(state)
        state = profile_extraction_node(state)
        state = scenario_router_node(state)
        state = risk_classifier_node(state)
        state = retrieval_planner_node(state)
        plan = retrieval_service.plan_retrieval(
            RetrievalPlanningInput(
                user_message=state.user_message,
                scenario=_scenario_value(graph_state, state),
                risk_level=_risk_level_value(graph_state, state),
                language=_language_value(graph_state, state),
                city=state.user_profile.city if state.user_profile else None,
            )
        )
        return {
            **graph_state,
            "agent_state": state,
            "retrieval_plan": plan,
            "graph_nodes_executed": _append_node(graph_state, "classify_or_plan"),
        }

    return node


def _retrieve_trusted_sources_node(
    retrieval_service: RetrievalService,
    source_registry: SourceRegistry,
    use_hybrid_rag: bool,
    semantic_retrieval_service: Any | None = None,
):
    def node(graph_state: LangGraphAgentState) -> LangGraphAgentState:
        state = graph_state["agent_state"]
        if state.risk_level in {RiskLevel.unsafe, RiskLevel.prompt_injection}:
            return {
                **graph_state,
                "retrieval_runtime": "blocked_by_safety",
                "graph_nodes_executed": _append_node(graph_state, "retrieve_trusted_sources"),
            }
        if (
            use_hybrid_rag
            and graph_state.get("use_hybrid_rag", True)
            and state.risk_level not in {RiskLevel.unsafe, RiskLevel.prompt_injection}
        ):
            try:
                hybrid_result = run_hybrid_rag_for_graph(
                    graph_state=graph_state,
                    source_registry=source_registry,
                    retrieval_service=retrieval_service,
                    semantic_retrieval_service=semantic_retrieval_service,
                )
                state.hybrid_rag_result = hybrid_result.model_dump(mode="json")
                state.selected_sources = _retrieved_sources_from_hybrid_rag(
                    hybrid_result,
                    source_registry,
                )
                state.citations = _hybrid_rag_citations(state.selected_sources)
                return {
                    **graph_state,
                    "agent_state": state,
                    "hybrid_rag_result": hybrid_result,
                    "retrieval_runtime": "hybrid_rag_v2",
                    "graph_nodes_executed": _append_node(
                        graph_state,
                        "retrieve_trusted_sources",
                    ),
                }
            except Exception as exc:
                _append_unique(
                    state.errors,
                    f"hybrid_rag: safe fallback to local retrieval after {type(exc).__name__}",
                )
                _append_unique(state.safety_flags, "hybrid_rag_safe_fallback")

        state = retrieval_node(
            graph_state["agent_state"],
            retrieval_service=retrieval_service,
        )
        state = citation_stub_node(state)
        return {
            **graph_state,
            "agent_state": state,
            "hybrid_rag_result": None,
            "retrieval_runtime": "local_keyword",
            "graph_nodes_executed": _append_node(graph_state, "retrieve_trusted_sources"),
        }

    return node


def _evaluate_source_coverage_node():
    def node(graph_state: LangGraphAgentState) -> LangGraphAgentState:
        state = graph_state["agent_state"]
        hybrid_result = graph_state.get("hybrid_rag_result")
        if hybrid_result is not None:
            for warning in hybrid_result.coverage.warnings:
                _append_unique(state.errors, f"hybrid_rag_coverage: {warning}")
            return {
                **graph_state,
                "agent_state": state,
                "retrieval_quality_report": hybrid_result.quality_report,
                "graph_nodes_executed": _append_node(
                    graph_state,
                    "evaluate_source_coverage",
                ),
            }

        plan = graph_state.get("retrieval_plan")
        report = build_retrieval_quality_report(
            RetrievalQualityInput(
                user_message=state.user_message,
                scenario=_scenario_value(graph_state, state),
                risk_level=_risk_level_value(graph_state, state),
                language=_language_value(graph_state, state),
                expected_source_types=list(getattr(plan, "required_source_types", []) or []),
            ),
            state.selected_sources,
            plan=plan,
        )
        for warning in report.warnings:
            _append_unique(state.errors, f"retrieval_quality: {warning}")
        return {
            **graph_state,
            "agent_state": state,
            "retrieval_quality_report": report,
            "graph_nodes_executed": _append_node(graph_state, "evaluate_source_coverage"),
        }

    return node


def _controlled_tool_decision_node():
    def node(graph_state: LangGraphAgentState) -> LangGraphAgentState:
        state = graph_state["agent_state"]
        plan = plan_tools(state)
        state.tool_decision = plan.model_dump(mode="json")
        return {
            **graph_state,
            "agent_state": state,
            "tool_plan": plan,
            "graph_nodes_executed": _append_node(graph_state, "controlled_tool_decision"),
        }

    return node


def _execute_agent_tools_node(graph_state: LangGraphAgentState) -> LangGraphAgentState:
    state = graph_state["agent_state"]
    receipts = execute_tools(state, graph_state["tool_plan"])
    state.tool_trace = {
        "mode": "local_allowlist",
        "used_network": False,
        "calls": [item.model_dump(mode="json") for item in receipts],
    }
    return {
        **graph_state,
        "agent_state": state,
        "graph_nodes_executed": _append_node(graph_state, "execute_agent_tools"),
    }


def _delivery_node(delivery):
    def node(graph_state: LangGraphAgentState) -> LangGraphAgentState:
        updated = {
            **graph_state,
            "graph_nodes_executed": _append_node(graph_state, "generate_and_verify_answer"),
        }
        # The adapter performs generation, claim review and the current-publication
        # delivery gate before this node completes. Standalone/offline graphs omit it.
        metadata = (
            delivery(_result_from_graph(updated)) if delivery else {"generation_mode": "offline"}
        )
        return {**updated, "delivery_metadata": metadata}

    return node


def _compose_grounded_answer_node():
    def node(graph_state: LangGraphAgentState) -> LangGraphAgentState:
        state = graph_state["agent_state"]
        hybrid_result = graph_state.get("hybrid_rag_result")
        if hybrid_result is not None:
            state = _compose_hybrid_grounded_answer(state, hybrid_result)
        else:
            state = grounded_answer_quality_node(state)
        return {
            **graph_state,
            "agent_state": state,
            "graph_nodes_executed": _append_node(graph_state, "compose_grounded_answer"),
        }

    return node


def _verify_safety_node():
    def node(graph_state: LangGraphAgentState) -> LangGraphAgentState:
        state = source_governance_node(graph_state["agent_state"])
        state = escalation_decider_node(state)
        _append_answer_quality_errors(state)
        _append_answer_verification_report(state, graph_state)
        return {
            **graph_state,
            "agent_state": state,
            "graph_nodes_executed": _append_node(graph_state, "verify_safety"),
        }

    return node


def _finalize_response_node():
    def node(graph_state: LangGraphAgentState) -> LangGraphAgentState:
        state = final_response_node(graph_state["agent_state"])
        updated_state = {
            **graph_state,
            "agent_state": state,
            "graph_nodes_executed": _append_node(graph_state, "finalize_response"),
        }
        return {
            **updated_state,
            "graph_metadata": _graph_metadata(updated_state),
        }

    return node


def _initial_agent_state(
    user_message: str,
    language: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    city: str | None = None,
    followup_scenario: UserScenario | None = None,
    followup_risk_level: RiskLevel | None = None,
) -> AgentState:
    state = AgentState(
        trace_id=str(uuid4()),
        user_id=user_id,
        session_id=session_id,
        user_message=user_message,
        preferred_language=_language_code(language),
        city=city,
        followup_scenario=followup_scenario,
        followup_risk_level=followup_risk_level,
    )
    language_code = _language_code(language)
    if language_code is not None:
        state.detected_language = language_code
        state.response_language = language_code
    return state


def run_hybrid_rag_for_graph(
    graph_state: LangGraphAgentState,
    source_registry: SourceRegistry,
    retrieval_service: RetrievalService,
    semantic_retrieval_service: Any | None = None,
) -> HybridRAGResult:
    state = graph_state["agent_state"]
    engine = HybridRAGEngine(
        source_registry=source_registry,
        retrieval_service=retrieval_service,
        semantic_retrieval_service=semantic_retrieval_service,
    )
    request = engine.build_request(
        user_message=state.user_message,
        scenario=_scenario_value(graph_state, state),
        risk_level=_risk_level_value(graph_state, state),
        language=_language_value(graph_state, state),
        include_answer_draft=True,
        use_semantic_retrieval=semantic_retrieval_service is not None,
        city=(state.user_profile.city if state.user_profile else None) or state.city,
    )
    return engine.run(request)


def _retrieved_sources_from_hybrid_rag(
    hybrid_result: HybridRAGResult,
    source_registry: SourceRegistry,
) -> list[RetrievedSource]:
    retrieved_sources: list[RetrievedSource] = []
    for item in hybrid_result.evidence:
        source = source_registry.get_source_by_id(item.source_id)
        if source is None:
            continue
        retrieved_sources.append(
            RetrievedSource(
                source=source,
                chunk_id=f"{item.source_id}::hybrid-rag-{item.rank}",
                content=item.excerpt,
                score=item.fused_score or item.score,
                rank=item.rank,
            )
        )
    return retrieved_sources


def _hybrid_rag_citations(selected_sources: list[RetrievedSource]) -> list[Citation]:
    citations: list[Citation] = []
    for retrieved_source in selected_sources:
        if not _is_official_or_curated_source(retrieved_source):
            continue
        citations.append(
            Citation(
                citation_id=f"CIT-{len(citations) + 1}",
                source_id=retrieved_source.source.source_id,
                claim=("Hybrid RAG selected this trusted source for grounded scenario context."),
                supporting_quote=retrieved_source.content,
                confidence=0.7,
            )
        )
    return citations


def _compose_hybrid_grounded_answer(
    state: AgentState,
    hybrid_result: HybridRAGResult,
) -> AgentState:
    if hybrid_result.answer_draft is None:
        return grounded_answer_quality_node(state)

    draft = GroundedAnswerDraft.model_validate(hybrid_result.answer_draft)
    by_id = {source.source.source_id: source for source in state.selected_sources}
    draft.source_notes = [
        build_source_note(by_id[note.source_id], used_for=note.used_for)
        if note.source_id in by_id
        else note
        for note in draft.source_notes
    ]
    checklist_items = (
        [item.title for item in state.checklist.items] if state.checklist is not None else []
    )
    coverage_warnings = list(hybrid_result.coverage.warnings)
    warning_values = [
        *draft.warnings,
        *([copy("verify", state.response_language.value)] if coverage_warnings else []),
    ]
    if state.unreviewed_source_candidate_count > 0:
        warning_values.append(copy("unreviewed", state.response_language.value))

    uncertainty_values = [
        *draft.uncertainty,
        *([copy("verify", state.response_language.value)] if coverage_warnings else []),
    ]
    draft = draft.model_copy(
        update={
            "checklist_items": checklist_items or draft.checklist_items,
            "unreviewed_candidate_count": state.unreviewed_source_candidate_count,
            "warnings": list(dict.fromkeys(warning_values)),
            "uncertainty": list(dict.fromkeys(uncertainty_values)),
        }
    )
    report = build_answer_quality_report(draft)
    state.grounded_answer = draft.model_dump(mode="json")
    state.answer_quality_report = report.model_dump(mode="json")
    state.draft_answer = render_grounded_answer_markdown(draft)
    return state


def _append_answer_quality_errors(state: AgentState) -> None:
    if not state.grounded_answer:
        _append_unique(state.errors, "answer_quality: missing grounded answer draft")
        return
    draft = GroundedAnswerDraft.model_validate(state.grounded_answer)
    report = build_answer_quality_report(draft)
    state.answer_quality_report = report.model_dump(mode="json")
    for issue in report.issues:
        if issue.severity in {"warning", "error"}:
            _append_unique(state.errors, f"answer_quality: {issue.code}: {issue.message}")


def _append_answer_verification_report(
    state: AgentState,
    graph_state: LangGraphAgentState,
) -> None:
    hybrid_result = graph_state.get("hybrid_rag_result")
    verify_agent_answer(
        state,
        domain=hybrid_result.domain if hybrid_result else state.scenario.value,
        evidence=hybrid_result.evidence if hybrid_result else state.selected_sources,
        coverage_warnings=_coverage_warnings_for_verification(graph_state),
    )


def _coverage_warnings_for_verification(graph_state: LangGraphAgentState) -> list[str]:
    hybrid_result = graph_state.get("hybrid_rag_result")
    if hybrid_result is not None:
        return list(dict.fromkeys(hybrid_result.coverage.warnings))
    return _retrieval_quality_warnings(graph_state.get("retrieval_quality_report"))


def _graph_metadata(graph_state: LangGraphAgentState) -> dict[str, Any]:
    state = graph_state["agent_state"]
    answer_quality_report = state.answer_quality_report or {}
    answer_verification_report = state.answer_verification_report or {}
    retrieval_quality_report = graph_state.get("retrieval_quality_report")
    hybrid_result = graph_state.get("hybrid_rag_result")
    coverage = hybrid_result.coverage if hybrid_result is not None else None
    retrieval_runtime = graph_state.get("retrieval_runtime", "local_keyword")
    return {
        **graph_state.get("delivery_metadata", {}),
        "graph_runtime": "langgraph",
        "retrieval_runtime": retrieval_runtime,
        "graph_nodes_executed": list(graph_state.get("graph_nodes_executed", [])),
        "agent_tool_decision": state.tool_decision,
        "agent_tool_trace": state.tool_trace,
        "used_network": bool(hybrid_result and hybrid_result.used_network)
        or bool(graph_state.get("delivery_metadata", {}).get("used_network")),
        "used_provider_call": bool(hybrid_result and hybrid_result.used_provider_call)
        or bool(graph_state.get("delivery_metadata", {}).get("used_provider_call")),
        "semantic_retrieval_diagnostics": (
            hybrid_result.semantic_retrieval_diagnostics if hybrid_result else {}
        ),
        "hybrid_rag_query_count": len(hybrid_result.query_runs) if hybrid_result is not None else 0,
        "hybrid_rag_evidence_count": len(hybrid_result.evidence)
        if hybrid_result is not None
        else 0,
        "unreviewed_source_candidate_count": state.unreviewed_source_candidate_count,
        "trusted_source_count": len(_unique_source_ids(state))
        if graph_state.get("delivery_metadata")
        else coverage.trusted_evidence_count
        if coverage is not None
        else len(_unique_source_ids(state)),
        "official_count": coverage.official_count if coverage is not None else 0,
        "curated_count": coverage.curated_count if coverage is not None else 0,
        "community_count": coverage.community_count if coverage is not None else 0,
        "has_official_or_curated": coverage.has_official_or_curated
        if coverage is not None
        else False,
        "coverage_warnings": list(coverage.warnings) if coverage is not None else [],
        "answer_quality_issue_count": len(answer_quality_report.get("issues", [])),
        "answer_verification_report": answer_verification_report,
        "answer_verification_passed": bool(answer_verification_report.get("passed", False)),
        "answer_verification_issue_count": len(answer_verification_report.get("issues", [])),
        "answer_verification_max_severity": answer_verification_report.get(
            "max_severity",
            "none",
        ),
        "unsupported_claim_count": int(
            answer_verification_report.get("unsupported_claim_count", 0)
        ),
        "retrieval_quality_warning_count": len(
            _retrieval_quality_warnings(retrieval_quality_report)
        ),
    }


def _scenario_value(graph_state: LangGraphAgentState, state: AgentState) -> str | None:
    return graph_state.get("scenario_hint") or state.scenario.value


def _risk_level_value(graph_state: LangGraphAgentState, state: AgentState) -> str | None:
    return graph_state.get("risk_level_hint") or state.risk_level.value


def _language_value(graph_state: LangGraphAgentState, state: AgentState) -> str | None:
    return graph_state.get("language_hint") or state.response_language.value


def _language_code(language: str | None) -> LanguageCode | None:
    if language is None:
        return None
    try:
        return LanguageCode(language)
    except ValueError:
        return None


def _unique_source_ids(state: AgentState) -> list[str]:
    source_ids: list[str] = []
    seen_source_ids: set[str] = set()
    for retrieved_source in state.selected_sources:
        source_id = retrieved_source.source.source_id
        if source_id in seen_source_ids:
            continue
        source_ids.append(source_id)
        seen_source_ids.add(source_id)
    return source_ids


def _is_official_or_curated_source(retrieved_source: RetrievedSource) -> bool:
    source_type = getattr(
        retrieved_source.source.source_type,
        "value",
        retrieved_source.source.source_type,
    )
    return source_type in {"official", "curated_guide"}


def _retrieval_quality_warnings(retrieval_quality_report: Any) -> list[str]:
    if retrieval_quality_report is None:
        return []
    if isinstance(retrieval_quality_report, dict):
        return list(retrieval_quality_report.get("warnings", []) or [])
    return list(getattr(retrieval_quality_report, "warnings", []) or [])


def _append_node(graph_state: LangGraphAgentState, node_name: str) -> list[str]:
    return [*graph_state.get("graph_nodes_executed", []), node_name]


def _append_unique(items: list[str], item: str) -> None:
    if item not in items:
        items.append(item)
