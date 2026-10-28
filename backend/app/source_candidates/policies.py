from hashlib import sha256

from backend.app.source_candidates.models import (
    SourceCandidate,
    SourceCandidateReviewDecision,
    utc_now,
)
from backend.app.tools.models import WebSearchCandidate
from backend.app.tools.policies import (
    COMMUNITY_DOMAIN_MARKERS,
    infer_domain_from_url,
)

_HIGH_RISK_LEVELS = {
    "high",
    "legal_sensitive",
    "work_status_sensitive",
    "medical_sensitive",
    "emergency",
    "unsafe",
}

_HIGH_RISK_TERMS = (
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
    "lost-passport",
    "consulate",
)

_OFFICIAL_SOURCE_TYPES = {"official", "curated_guide"}
_OFFICIAL_TRUST_LEVELS = {"level_1_official", "level_2_curated"}
_UNTRUSTED_SOURCE_TYPES = {"untrusted"}
_UNTRUSTED_TRUST_LEVELS = {"level_6_untrusted"}


def candidate_requires_manual_review(candidate: SourceCandidate) -> bool:
    if candidate.status in {"approved", "rejected"}:
        return False
    return candidate.requires_review or candidate.status in {"pending", "needs_review"}


def candidate_can_be_retrievable(candidate: SourceCandidate) -> bool:
    if candidate.status != "approved":
        return False
    if candidate.requires_review:
        return False
    if not candidate.allow_retrieval:
        return False
    if not candidate.assigned_source_type or not candidate.assigned_trust_level:
        return False
    if candidate.assigned_source_type in _UNTRUSTED_SOURCE_TYPES:
        return False
    return candidate.assigned_trust_level not in _UNTRUSTED_TRUST_LEVELS


def validate_review_decision(
    candidate: SourceCandidate,
    decision: SourceCandidateReviewDecision,
) -> list[str]:
    warnings: list[str] = []

    if decision.candidate_id != candidate.candidate_id:
        warnings.append("Review decision candidate_id does not match candidate.")
    if not decision.reviewer_id.strip():
        warnings.append("Review decision requires reviewer_id.")
    if not decision.reason.strip():
        warnings.append("Review decision requires reason.")

    if decision.action == "reject":
        if not decision.reason.strip():
            warnings.append("Reject action requires reason.")
        return list(dict.fromkeys(warnings))

    if decision.action == "needs_review":
        return list(dict.fromkeys(warnings))

    if not decision.assigned_source_type:
        warnings.append("Approve action requires assigned_source_type.")
    if not decision.assigned_trust_level:
        warnings.append("Approve action requires assigned_trust_level.")

    if decision.allow_retrieval and (
        not decision.assigned_source_type or not decision.assigned_trust_level
    ):
        warnings.append("Retrieval permission requires assigned source_type and trust_level.")

    if candidate_is_high_risk(candidate):
        if not decision.reason.strip():
            warnings.append("High-risk approval requires reason.")
        if not decision.freshness_note or not decision.freshness_note.strip():
            warnings.append("High-risk approval requires freshness_note.")
        if decision.allow_retrieval and decision.assigned_source_type not in _OFFICIAL_SOURCE_TYPES:
            warnings.append(
                "High-risk retrievable approval should be official or curated for official claims."
            )
        if decision.allow_retrieval and decision.assigned_trust_level not in _OFFICIAL_TRUST_LEVELS:
            warnings.append(
                "High-risk retrievable approval should use official or curated trust level."
            )

    if decision.assigned_source_type == "official" and not candidate.official_domain_hint:
        warnings.append("Official source_type assigned without an official domain hint.")

    if decision.assigned_source_type == "official" and _is_community_style_candidate(candidate):
        warnings.append(
            "Community, blog, forum, or social candidate assigned official source_type."
        )

    return list(dict.fromkeys(warnings))


def should_require_freshness_note(candidate: SourceCandidate) -> bool:
    return candidate_is_high_risk(candidate)


def candidate_is_high_risk(candidate: SourceCandidate) -> bool:
    if (candidate.risk_level or "").casefold() in _HIGH_RISK_LEVELS:
        return True
    searchable = " ".join(
        value
        for value in [
            candidate.scenario,
            candidate.title,
            candidate.snippet,
            candidate.url,
        ]
        if value
    ).casefold()
    return any(term in searchable for term in _HIGH_RISK_TERMS)


def candidate_from_web_search_candidate(
    web_candidate: WebSearchCandidate,
    scenario: str | None = None,
    risk_level: str | None = None,
) -> SourceCandidate:
    domain = web_candidate.domain or infer_domain_from_url(web_candidate.url)
    candidate_key = f"{web_candidate.url}|{web_candidate.title}".encode()
    candidate_id = f"SRC-CAND-{sha256(candidate_key).hexdigest()[:12].upper()}"
    return SourceCandidate(
        candidate_id=candidate_id,
        title=web_candidate.title,
        url=web_candidate.url,
        snippet=web_candidate.snippet,
        domain=domain,
        source_type_guess=web_candidate.source_type_guess,
        trust_guess=web_candidate.trust_guess,
        language=web_candidate.language,
        scenario=scenario,
        risk_level=risk_level,
        official_domain_hint=web_candidate.official_domain_hint,
        requires_review=True,
        status="pending",
        warnings=list(web_candidate.warnings),
        discovered_by="offline_tool_contract",
        created_at=utc_now(),
    )


def _is_community_style_candidate(candidate: SourceCandidate) -> bool:
    domain = (candidate.domain or infer_domain_from_url(candidate.url) or "").casefold()
    if any(marker in domain for marker in COMMUNITY_DOMAIN_MARKERS):
        return True
    guess = (candidate.source_type_guess or "").casefold()
    return "community" in guess or guess in {"blog", "forum", "social"}
