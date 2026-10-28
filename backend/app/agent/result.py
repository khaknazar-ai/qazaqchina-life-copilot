from pydantic import BaseModel, Field

from backend.app.domain.agent import AgentState
from backend.app.domain.enums import RiskLevel, UserScenario
from backend.app.domain.sources import Citation


class AgentWorkflowResult(BaseModel):
    state: AgentState
    answer: str
    trace_id: str
    scenario: UserScenario
    risk_level: RiskLevel
    escalation_required: bool
    citations: list[Citation] = Field(default_factory=list)
    selected_source_ids: list[str] = Field(default_factory=list)
    node_sequence: list[str] = Field(default_factory=list)
    safety_flags: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class NodeResult(BaseModel):
    node_name: str
    state: AgentState
