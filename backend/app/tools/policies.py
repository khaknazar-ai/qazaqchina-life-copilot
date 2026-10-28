from urllib.parse import urlparse

from backend.app.retrieval.planner import RetrievalPlan
from backend.app.tools.models import ToolCallRequest, ToolSafetyLevel, WebSearchCandidate

OFFICIAL_DOMAIN_MARKERS = (
    ".gov",
    ".gov.cn",
    ".edu",
    "embassy.",
    "consulate.",
    "police.",
    "hospital.",
    "university.",
    "alipay.",
    "wechat.",
)

COMMUNITY_DOMAIN_MARKERS = (
    "forum.",
    "blog.",
    "community.",
    "social.",
    "telegram.",
    "reddit.",
)

SENSITIVE_TERMS = (
    "passport",
    "visa",
    "overstay",
    "registration",
    "police",
    "work",
    "contract",
    "medical",
    "hospital",
    "emergency",
)

SENSITIVE_RISK_LEVELS = {
    "high",
    "legal_sensitive",
    "work_status_sensitive",
    "medical_sensitive",
    "emergency",
    "unsafe",
    "prompt_injection",
}


def infer_domain_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    domain = parsed.netloc.casefold()
    if not domain:
        return None
    return domain.removeprefix("www.")


def looks_like_official_domain(url: str) -> bool:
    domain = infer_domain_from_url(url)
    if domain is None:
        return False
    return any(marker in domain for marker in OFFICIAL_DOMAIN_MARKERS)


def guess_source_type_from_url(url: str) -> str:
    domain = infer_domain_from_url(url) or ""
    if looks_like_official_domain(url):
        return "official"
    if any(marker in domain for marker in COMMUNITY_DOMAIN_MARKERS):
        return "ordinary_community"
    return "unreviewed_web_candidate"


def build_tool_query_from_retrieval_plan(plan: RetrievalPlan) -> list[str]:
    queries: list[str] = []
    for query in plan.queries:
        if query.query not in queries:
            queries.append(query.query)
    return queries


def evaluate_tool_request_safety(
    request: ToolCallRequest,
    plan: RetrievalPlan | None = None,
) -> tuple[ToolSafetyLevel, list[str], str | None]:
    warnings = ["Offline contract only; web candidates require review before source registry use."]

    if request.tool_name != "fake_web_search":
        return "blocked", warnings, f"Unsupported offline tool: {request.tool_name}"

    if _is_sensitive_request(request, plan):
        warnings.append(
            "High-risk discovery is manual-review-required and cannot auto-trust results."
        )
        return "manual_review_required", warnings, None

    return "safe_offline", warnings, None


def candidate_from_fake_result(
    title: str,
    url: str,
    snippet: str,
    language: str | None = None,
) -> WebSearchCandidate:
    domain = infer_domain_from_url(url)
    official_hint = looks_like_official_domain(url)
    source_type_guess = guess_source_type_from_url(url)
    warnings = [
        "Candidate requires manual review before registry ingestion or citation use.",
        "Source type is only a URL-based guess, not a trust assignment.",
    ]

    if official_hint:
        trust_guess = "level_1_official_candidate"
        warnings.append("Official-looking domain is a hint only; verify ownership and freshness.")
    else:
        trust_guess = "unreviewed_candidate"
        warnings.append("Non-official-looking candidate cannot support official claims.")

    if _text_has_sensitive_terms(f"{title} {snippet} {url}"):
        warnings.append("Sensitive-domain candidate: official verification required.")

    if source_type_guess == "ordinary_community":
        warnings.append("Community or forum content is practical context only, never official law.")

    return WebSearchCandidate(
        title=title,
        url=url,
        snippet=snippet,
        domain=domain,
        source_type_guess=source_type_guess,
        trust_guess=trust_guess,
        language=language,
        official_domain_hint=official_hint,
        requires_review=True,
        warnings=list(dict.fromkeys(warnings)),
    )


def add_plan_warnings_to_candidate(
    candidate: WebSearchCandidate,
    plan: RetrievalPlan | None,
) -> WebSearchCandidate:
    if plan is None or not plan.source_policy.require_official or candidate.official_domain_hint:
        return candidate

    warnings = [
        *candidate.warnings,
        "Retrieval plan requires official sources; this candidate is not official-looking.",
    ]
    return candidate.model_copy(update={"warnings": list(dict.fromkeys(warnings))})


def _is_sensitive_request(request: ToolCallRequest, plan: RetrievalPlan | None) -> bool:
    if (request.risk_level or "").casefold() in SENSITIVE_RISK_LEVELS:
        return True
    if plan is not None and (
        plan.source_policy.require_official or plan.source_policy.needs_human_escalation_context
    ):
        return True
    return _text_has_sensitive_terms(f"{request.scenario or ''} {request.query}")


def _text_has_sensitive_terms(text: str) -> bool:
    normalized = text.casefold()
    return any(term in normalized for term in SENSITIVE_TERMS)
