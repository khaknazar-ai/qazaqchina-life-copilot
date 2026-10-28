from typing import Literal

from pydantic import BaseModel, Field

ToolSafetyLevel = Literal["safe_offline", "manual_review_required", "blocked"]


class ToolCallRequest(BaseModel):
    tool_name: str
    query: str
    scenario: str | None = None
    risk_level: str | None = None
    language: str | None = None
    country: str | None = "CN"
    city: str | None = None
    max_results: int = Field(default=5, gt=0)


class WebSearchCandidate(BaseModel):
    title: str
    url: str
    snippet: str
    domain: str | None = None
    source_type_guess: str | None = None
    trust_guess: str | None = None
    language: str | None = None
    published_at: str | None = None
    official_domain_hint: bool = False
    requires_review: bool = True
    warnings: list[str] = Field(default_factory=list)


class ToolCallResult(BaseModel):
    tool_name: str
    query: str
    safety_level: ToolSafetyLevel
    candidates: list[WebSearchCandidate] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    blocked_reason: str | None = None
    used_network: bool = False


class ToolTrace(BaseModel):
    tool_name: str
    query: str
    scenario: str | None = None
    risk_level: str | None = None
    used_network: bool = False
    candidate_count: int = 0
    warnings: list[str] = Field(default_factory=list)
    blocked_reason: str | None = None
