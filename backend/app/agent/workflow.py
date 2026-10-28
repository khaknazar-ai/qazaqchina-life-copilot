from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.app.agent.nodes import (
    answer_generation_stub_node,
    citation_stub_node,
    escalation_decider_node,
    final_response_node,
    generate_checklist_node,
    grounded_answer_quality_node,
    input_guard_node,
    language_detector_node,
    profile_extraction_node,
    retrieval_node,
    retrieval_planner_node,
    risk_classifier_node,
    scenario_router_node,
    source_governance_node,
    tool_decision_node,
    tool_execution_stub_node,
)
from backend.app.agent.result import AgentWorkflowResult
from backend.app.checklist_engine.service import ChecklistEngineService
from backend.app.domain.agent import AgentState
from backend.app.domain.enums import LanguageCode, RiskLevel, UserScenario
from backend.app.escalation.service import EscalationService
from backend.app.retrieval.service import RetrievalService
from backend.app.services.trace_service import TraceService
from backend.app.source_governance.service import SourceGovernanceService
from backend.app.source_registry.registry import SourceRegistry
from backend.app.verification.gate import verify_agent_answer

AgentNode = Callable[[AgentState], AgentState]


class DeterministicAgentWorkflow:
    def __init__(
        self,
        source_registry: SourceRegistry | None = None,
        retrieval_service: RetrievalService | None = None,
        source_governance_service: SourceGovernanceService | None = None,
        escalation_service: EscalationService | None = None,
        checklist_engine_service: ChecklistEngineService | None = None,
        trace_service: TraceService | None = None,
        semantic_retrieval_service: Any | None = None,
    ) -> None:
        self.source_registry = source_registry or SourceRegistry.from_data_dir(Path("data/sources"))
        self.retrieval_service = retrieval_service or RetrievalService(
            source_registry=self.source_registry
        )
        self.source_governance_service = source_governance_service or SourceGovernanceService()
        self.escalation_service = escalation_service or EscalationService()
        self.checklist_engine_service = checklist_engine_service or ChecklistEngineService()
        self.trace_service = trace_service
        self.semantic_retrieval_service = semantic_retrieval_service
        self.nodes: list[tuple[str, AgentNode]] = [
            ("input_guard", input_guard_node),
            ("language_detector", language_detector_node),
            ("profile_extractor", profile_extraction_node),
            ("scenario_router", scenario_router_node),
            ("risk_classifier", risk_classifier_node),
            ("retrieval_planner", retrieval_planner_node),
            ("retrieval_node", self._retrieval_node),
            ("tool_decision", tool_decision_node),
            ("tool_execution_stub", tool_execution_stub_node),
            ("answer_generation_stub", answer_generation_stub_node),
            ("citation_stub", citation_stub_node),
            ("source_governance_node", self._source_governance_node),
            ("escalation_decider", self._escalation_decider_node),
            ("generate_checklist_node", self._generate_checklist_node),
            ("grounded_answer_quality_node", grounded_answer_quality_node),
            ("verify_answer", verify_agent_answer),
            ("trace_writer", self._trace_writer_node),
            ("final_response", final_response_node),
        ]

    def run(
        self,
        user_message: str,
        user_id: str | None = None,
        session_id: str | None = None,
        preferred_language: LanguageCode | None = None,
        city: str | None = None,
        followup_scenario: UserScenario | None = None,
        followup_risk_level: RiskLevel | None = None,
    ) -> AgentWorkflowResult:
        trace_id = self.trace_service.generate_trace_id() if self.trace_service else str(uuid4())
        initial_state = AgentState(
            trace_id=trace_id,
            user_id=user_id,
            session_id=session_id,
            user_message=user_message,
            preferred_language=preferred_language,
            city=city,
            followup_scenario=followup_scenario,
            followup_risk_level=followup_risk_level,
        )
        return self.run_state(initial_state)

    def run_state(self, initial_state: AgentState) -> AgentWorkflowResult:
        state = initial_state
        node_sequence: list[str] = []

        self._log_workflow_start(state)
        for node_name, node in self.nodes:
            self._log_node_event("node_start", node_name, state)
            state = node(state)
            node_sequence.append(node_name)
            self._log_node_event("node_end", node_name, state)
        self._log_workflow_end(state, node_sequence)

        return AgentWorkflowResult(
            state=state,
            answer=state.final_answer or "",
            trace_id=state.trace_id,
            scenario=state.scenario,
            risk_level=state.risk_level,
            escalation_required=state.escalation_required,
            citations=state.citations,
            selected_source_ids=_unique_source_ids(state),
            node_sequence=node_sequence,
            safety_flags=state.safety_flags,
            metadata={
                "graph_runtime": "deterministic",
                "graph_nodes_executed": node_sequence,
                "used_network": bool((state.hybrid_rag_result or {}).get("used_network")),
                "used_provider_call": bool(
                    (state.hybrid_rag_result or {}).get("used_provider_call")
                ),
                "semantic_retrieval_diagnostics": (state.hybrid_rag_result or {}).get(
                    "semantic_retrieval_diagnostics", {}
                ),
                "unreviewed_source_candidate_count": (state.unreviewed_source_candidate_count),
                "trusted_source_count": len(_unique_source_ids(state)),
                "answer_quality_issue_count": len(
                    (state.answer_quality_report or {}).get("issues", [])
                ),
            },
        )

    def _retrieval_node(self, state: AgentState) -> AgentState:
        if self.semantic_retrieval_service is not None and state.risk_level not in {
            RiskLevel.unsafe, RiskLevel.prompt_injection,
        }:
            from backend.app.agent.langgraph_workflow import (
                _hybrid_rag_citations,
                _retrieved_sources_from_hybrid_rag,
                run_hybrid_rag_for_graph,
            )

            result = run_hybrid_rag_for_graph(
                graph_state={"agent_state": state, "graph_nodes_executed": []},
                source_registry=self.source_registry,
                retrieval_service=self.retrieval_service,
                semantic_retrieval_service=self.semantic_retrieval_service,
            )
            state.hybrid_rag_result = result.model_dump(mode="json")
            state.selected_sources = _retrieved_sources_from_hybrid_rag(
                result, self.source_registry,
            )
            state.citations = _hybrid_rag_citations(state.selected_sources)
            return state
        return retrieval_node(state, retrieval_service=self.retrieval_service)

    def _source_governance_node(self, state: AgentState) -> AgentState:
        return source_governance_node(
            state,
            source_governance_service=self.source_governance_service,
        )

    def _escalation_decider_node(self, state: AgentState) -> AgentState:
        return escalation_decider_node(state, escalation_service=self.escalation_service)

    def _generate_checklist_node(self, state: AgentState) -> AgentState:
        return generate_checklist_node(
            state,
            checklist_engine_service=self.checklist_engine_service,
        )

    def _trace_writer_node(self, state: AgentState) -> AgentState:
        return state

    def _log_workflow_start(self, state: AgentState) -> None:
        if not self.trace_service:
            return
        self.trace_service.log_event(
            event_type="workflow_start",
            trace_id=state.trace_id,
            payload={
                "message_length": len(state.user_message),
                "has_user_id": state.user_id is not None,
                "has_session_id": state.session_id is not None,
            },
        )

    def _log_workflow_end(self, state: AgentState, node_sequence: list[str]) -> None:
        if not self.trace_service:
            return
        self.trace_service.log_event(
            event_type="workflow_end",
            trace_id=state.trace_id,
            payload={
                "scenario": state.scenario.value,
                "risk_level": state.risk_level.value,
                "escalation_required": state.escalation_required,
                "node_count": len(node_sequence),
                "selected_source_count": len(state.selected_sources),
            },
        )

    def _log_node_event(self, event_type: str, node_name: str, state: AgentState) -> None:
        if not self.trace_service:
            return
        self.trace_service.log_event(
            event_type=event_type,
            trace_id=state.trace_id,
            payload={
                "node_name": node_name,
                "message_length": len(state.user_message),
                "scenario": state.scenario.value,
                "risk_level": state.risk_level.value,
                "safety_flag_count": len(state.safety_flags),
                **self._node_trace_payload(node_name, state),
            },
        )

    @staticmethod
    def _node_trace_payload(node_name: str, state: AgentState) -> dict:
        if node_name == "retrieval_node":
            return {
                "selected_source_count": len(state.selected_sources),
                "selected_source_ids": _unique_source_ids(state),
                "include_community": state.risk_level
                not in {
                    RiskLevel.legal_sensitive,
                    RiskLevel.work_status_sensitive,
                    RiskLevel.medical_sensitive,
                    RiskLevel.emergency,
                    RiskLevel.unsafe,
                    RiskLevel.prompt_injection,
                },
            }
        if node_name == "tool_decision":
            return {
                "tool_decision": state.tool_decision,
                "tool_trace": state.tool_trace,
                "unreviewed_source_candidate_count": (state.unreviewed_source_candidate_count),
            }
        if node_name == "source_governance_node":
            return {
                "citation_count": len(state.citations),
                "error_count": len(state.errors),
                "source_governance_failed": "source_governance_failed" in state.safety_flags,
            }
        if node_name == "escalation_decider":
            return {
                "escalation_required": state.escalation_required,
                "escalation_reason_count": len(state.escalation_reasons),
            }
        if node_name == "generate_checklist_node":
            return {
                "has_checklist": state.checklist is not None,
                "checklist_item_count": len(state.checklist.items) if state.checklist else 0,
            }
        if node_name == "grounded_answer_quality_node":
            report = state.answer_quality_report or {}
            return {
                "has_grounded_answer": state.grounded_answer is not None,
                "answer_quality_issue_count": len(report.get("issues", [])),
                "trusted_source_count": report.get("trusted_source_count", 0),
            }
        return {}


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
