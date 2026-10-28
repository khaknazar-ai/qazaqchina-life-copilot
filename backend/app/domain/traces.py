from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from backend.app.domain.enums import RiskLevel, UserScenario


class TraceRecord(BaseModel):
    trace_id: str
    user_id: str | None = None
    session_id: str | None = None
    timestamp: datetime
    scenario: UserScenario = UserScenario.unclear
    risk_level: RiskLevel = RiskLevel.normal
    node_sequence: list[str] = Field(default_factory=list)
    retrieved_source_ids: list[str] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    source_conflict_ids: list[str] = Field(default_factory=list)
    final_answer: str | None = None
    escalation_required: bool = False
    errors: list[str] = Field(default_factory=list)
