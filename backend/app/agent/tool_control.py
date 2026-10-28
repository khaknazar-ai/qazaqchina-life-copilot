from pydantic import BaseModel, Field

from backend.app.retrieval.planner import (
    RetrievalPlanningInput,
    build_retrieval_plan,
)
from backend.app.source_candidates.models import SourceCandidate
from backend.app.source_candidates.policies import candidate_can_be_retrievable
from backend.app.source_candidates.service import SourceCandidateQueueService
from backend.app.tools.service import ToolDiscoveryService

_SENSITIVE_RISK_LEVELS = {
    "high",
    "legal_sensitive",
    "work_status_sensitive",
    "medical_sensitive",
    "emergency",
    "unsafe",
    "prompt_injection",
}
_DISCOVERY_TERMS = (
    "passport",
    "visa",
    "overstay",
    "registration",
    "police",
    "work",
    "contract",
    "medical",
    "hospital",
    "payment",
    "scam",
    "wechat",
    "alipay",
    "university",
    "consulate",
    "embassy",
)


class AgentToolDecision(BaseModel):
    should_run_tools: bool
    tool_mode: str = "offline_fake_only"
    reason: str
    scenario: str | None = None
    risk_level: str | None = None
    allowed_tool_names: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AgentToolExecutionResult(BaseModel):
    decision: AgentToolDecision
    used_network: bool = False
    candidate_count: int = 0
    source_candidate_count: int = 0
    warnings: list[str] = Field(default_factory=list)
    trace_payload: dict = Field(default_factory=dict)


def should_consider_tool_discovery(
    user_message: str,
    scenario: str | None = None,
    risk_level: str | None = None,
) -> bool:
    plan = build_retrieval_plan(
        RetrievalPlanningInput(
            user_message=user_message,
            scenario=scenario,
            risk_level=risk_level,
        )
    )
    if plan.source_policy.require_official or plan.source_policy.require_freshness_check:
        return True
    if (risk_level or "").casefold() in _SENSITIVE_RISK_LEVELS:
        return True
    normalized = f"{scenario or ''} {user_message}".casefold()
    return any(term in normalized for term in _DISCOVERY_TERMS)


def build_agent_tool_decision(
    user_message: str,
    scenario: str | None = None,
    risk_level: str | None = None,
) -> AgentToolDecision:
    plan = build_retrieval_plan(
        RetrievalPlanningInput(
            user_message=user_message,
            scenario=scenario,
            risk_level=risk_level,
        )
    )
    warnings = [
        "Offline fake discovery only; tool results are unreviewed source candidates.",
        "Tool candidates must not be used as trusted citations.",
    ]
    if (risk_level or plan.risk_level or "").casefold() in _SENSITIVE_RISK_LEVELS:
        warnings.append("manual review required")
    if plan.source_policy.require_official:
        warnings.append("Official-looking tool candidates remain hints until reviewed.")

    should_run = should_consider_tool_discovery(user_message, scenario, risk_level)
    return AgentToolDecision(
        should_run_tools=should_run,
        reason=(
            "Retrieval policy or sensitive terms recommend offline source-candidate discovery."
            if should_run
            else "No controlled tool discovery needed for this low-risk general request."
        ),
        scenario=scenario or plan.scenario,
        risk_level=risk_level or plan.risk_level,
        allowed_tool_names=["fake_web_search"] if should_run else [],
        warnings=list(dict.fromkeys(warnings if should_run else warnings[:2])),
    )


def run_controlled_offline_tool_discovery(
    user_message: str,
    scenario: str | None = None,
    risk_level: str | None = None,
    language: str | None = None,
    city: str | None = None,
) -> AgentToolExecutionResult:
    decision = build_agent_tool_decision(
        user_message=user_message,
        scenario=scenario,
        risk_level=risk_level,
    )
    if not decision.should_run_tools:
        return _execution_result(decision=decision, warnings=decision.warnings)

    planning_input = RetrievalPlanningInput(
        user_message=user_message,
        scenario=scenario,
        risk_level=risk_level,
        language=language,
        city=city,
    )
    tool_results = ToolDiscoveryService().run_fake_web_discovery(planning_input)
    web_candidates = [
        candidate for result in tool_results for candidate in result.candidates
    ]
    queue = SourceCandidateQueueService()
    queue.add_from_web_candidates(
        web_candidates,
        scenario=scenario,
        risk_level=risk_level,
    )
    source_candidates = queue.list_candidates()
    warnings = list(
        dict.fromkeys(
            [
                *decision.warnings,
                *[warning for result in tool_results for warning in result.warnings],
                *[warning for candidate in source_candidates for warning in candidate.warnings],
            ]
        )
    )
    if any(candidate_can_be_retrievable(candidate) for candidate in source_candidates):
        warnings.append("Unexpected retrievable tool candidate blocked from trusted use.")

    used_network = any(result.used_network for result in tool_results)
    status_counts = _source_candidate_status_counts(source_candidates)
    return _execution_result(
        decision=decision,
        used_network=used_network,
        candidate_count=len(web_candidates),
        source_candidate_count=len(source_candidates),
        warnings=warnings,
        source_candidate_status_counts=status_counts,
        source_candidate_requires_review_count=sum(
            1 for candidate in source_candidates if candidate.requires_review
        ),
        retrievable_source_candidate_count=sum(
            1
            for candidate in source_candidates
            if candidate_can_be_retrievable(candidate)
        ),
    )


def _execution_result(
    decision: AgentToolDecision,
    used_network: bool = False,
    candidate_count: int = 0,
    source_candidate_count: int = 0,
    warnings: list[str] | None = None,
    source_candidate_status_counts: dict[str, int] | None = None,
    source_candidate_requires_review_count: int = 0,
    retrievable_source_candidate_count: int = 0,
) -> AgentToolExecutionResult:
    warning_values = list(dict.fromkeys(warnings or []))
    trace_payload = {
        "tool_mode": decision.tool_mode,
        "used_network": used_network,
        "candidate_count": candidate_count,
        "source_candidate_count": source_candidate_count,
        "source_candidate_status_counts": source_candidate_status_counts or {},
        "source_candidate_requires_review_count": (
            source_candidate_requires_review_count
        ),
        "retrievable_source_candidate_count": retrievable_source_candidate_count,
        "warning_count": len(warning_values),
        "allowed_tool_names": decision.allowed_tool_names,
    }
    return AgentToolExecutionResult(
        decision=decision,
        used_network=used_network,
        candidate_count=candidate_count,
        source_candidate_count=source_candidate_count,
        warnings=warning_values,
        trace_payload=trace_payload,
    )


def _source_candidate_status_counts(candidates: list[SourceCandidate]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for candidate in candidates:
        counts[candidate.status] = counts.get(candidate.status, 0) + 1
    return counts
