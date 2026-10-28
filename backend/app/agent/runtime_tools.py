"""Bounded, local agent tools. None creates a case or sends a support request."""

from collections.abc import Callable
from enum import StrEnum

from pydantic import BaseModel, Field

from backend.app.agent.nodes import (
    escalation_decider_node,
    generate_checklist_node,
    source_governance_node,
)
from backend.app.domain.agent import AgentState
from backend.app.domain.enums import RiskLevel, UserScenario


class AgentToolName(StrEnum):
    check_source_policy = "check_source_policy"
    build_checklist = "build_checklist"
    prepare_handoff = "prepare_handoff"


class ToolReceipt(BaseModel):
    name: AgentToolName
    status: str
    output_count: int = 0
    error_code: str | None = None


class AgentToolPlan(BaseModel):
    names: list[AgentToolName] = Field(default_factory=list, max_length=3)
    reason: str


_BLOCKED = {RiskLevel.unsafe, RiskLevel.prompt_injection}
_CHECKLIST_SCENARIOS = {
    UserScenario.tourism,
    UserScenario.kazakhstan_entry,
    UserScenario.study,
    UserScenario.work,
    UserScenario.medical,
    UserScenario.emergency,
    UserScenario.payments,
    UserScenario.housing,
}
_SENSITIVE = {
    RiskLevel.legal_sensitive,
    RiskLevel.work_status_sensitive,
    RiskLevel.medical_sensitive,
    RiskLevel.emergency,
}


def plan_tools(state: AgentState) -> AgentToolPlan:
    if state.risk_level in _BLOCKED:
        return AgentToolPlan(reason="unsafe_request")
    names = [AgentToolName.check_source_policy] if state.selected_sources else []
    if state.scenario in _CHECKLIST_SCENARIOS:
        names.append(AgentToolName.build_checklist)
    if state.risk_level in _SENSITIVE or not state.selected_sources:
        names.append(AgentToolName.prepare_handoff)
    return AgentToolPlan(names=names, reason="scenario_and_source_coverage")


def execute_tools(state: AgentState, plan: AgentToolPlan) -> list[ToolReceipt]:
    # Resolve only this allowlist; user/model text can never name an executable.
    handlers: dict[AgentToolName, Callable[[AgentState], AgentState]] = {
        AgentToolName.check_source_policy: source_governance_node,
        AgentToolName.build_checklist: generate_checklist_node,
        AgentToolName.prepare_handoff: escalation_decider_node,
    }
    receipts = []
    for name in dict.fromkeys(plan.names):
        if state.risk_level in _BLOCKED:
            receipts.append(ToolReceipt(name=name, status="blocked"))
            continue
        try:
            handlers[name](state)
            count = {
                AgentToolName.check_source_policy: len(state.selected_sources),
                AgentToolName.build_checklist: len(state.checklist.items) if state.checklist else 0,
                AgentToolName.prepare_handoff: int(state.escalation_required),
            }[name]
            receipts.append(ToolReceipt(name=name, status="completed", output_count=count))
        except Exception as exc:
            # Never put exception messages (possibly containing private inputs) in traces.
            if name == AgentToolName.build_checklist:
                state.checklist = None
            state.safety_flags.append("agent_tool_failed")
            state.errors.append(f"agent_tool:{name}:{type(exc).__name__}")
            receipts.append(
                ToolReceipt(
                    name=name,
                    status="failed",
                    error_code=type(exc).__name__,
                )
            )
    return receipts
