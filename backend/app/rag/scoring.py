from typing import Any

COMMUNITY_SOURCE_TYPES = {
    "verified_institutional_contributor",
    "verified_experienced_contributor",
    "ordinary_community",
}
OFFICIAL_SOURCE_TYPES = {"official", "curated_guide"}
UNTRUSTED_SOURCE_TYPES = {"untrusted", "candidate", "unreviewed_candidate"}
UNTRUSTED_LEVELS = {"level_6_untrusted", "untrusted"}
SENSITIVE_DOMAINS = {
    "passport_document_loss",
    "visa_overstay_registration",
    "work_contract_status",
    "medical_hospital",
    "emergency",
}
SENSITIVE_RISK_LEVELS = {
    "high",
    "legal_sensitive",
    "work_status_sensitive",
    "medical_sensitive",
    "emergency",
    "unsafe",
    "prompt_injection",
}

_SOURCE_TYPE_RANKS = {
    "official": 1,
    "curated_guide": 2,
    "verified_institutional_contributor": 3,
    "verified_experienced_contributor": 4,
    "ordinary_community": 5,
    "untrusted": 6,
    "candidate": 6,
    "unreviewed_candidate": 6,
}
_TRUST_LEVEL_RANKS = {
    "level_1_official": 1,
    "level_2_curated": 2,
    "level_3_verified_institutional": 3,
    "level_4_verified_experienced": 4,
    "level_5_ordinary_community": 5,
    "level_6_untrusted": 6,
}
_POLICY_BOOSTS = {
    1: 3.0,
    2: 2.0,
    3: 1.1,
    4: 0.8,
    5: 0.25,
    6: -10.0,
}


def source_type_rank(source_type: str | None, trust_level: str | None = None) -> int:
    normalized_source_type = _normalize(source_type)
    normalized_trust_level = _normalize(trust_level)
    if normalized_source_type in _SOURCE_TYPE_RANKS:
        return _SOURCE_TYPE_RANKS[normalized_source_type]
    if normalized_trust_level in _TRUST_LEVEL_RANKS:
        return _TRUST_LEVEL_RANKS[normalized_trust_level]
    return 6


def source_policy_boost(
    source: Any,
    domain: str,
    risk_level: str | None = None,
) -> float:
    source_type = _source_type(source)
    rank = source_type_rank(source_type, _trust_level(source))
    boost = _POLICY_BOOSTS.get(rank, -10.0)

    if _official_required_context(domain, risk_level):
        if source_type == "official":
            boost += 2.0
        elif source_type == "curated_guide":
            boost += 1.0
        elif source_type in COMMUNITY_SOURCE_TYPES:
            boost -= 1.0

    return boost


def source_policy_warnings(
    source: Any,
    domain: str,
    risk_level: str | None = None,
) -> list[str]:
    source_type = _source_type(source)
    trust_level = _trust_level(source)
    warnings: list[str] = []

    if source_type in UNTRUSTED_SOURCE_TYPES or trust_level in UNTRUSTED_LEVELS:
        warnings.append("Untrusted or unreviewed source cannot be used as hybrid evidence.")

    if not bool(getattr(_source_reference(source), "allow_ai_retrieval", True)):
        warnings.append("Source is not allowed for AI retrieval.")

    if source_type in COMMUNITY_SOURCE_TYPES:
        warnings.append(
            "Community or contributor source is practical context only, not official authority."
        )
        if _official_required_context(domain, risk_level):
            warnings.append(
                "Community context must not ground official legal, administrative, medical, "
                "passport, visa, or work-status claims."
            )

    return list(dict.fromkeys(warnings))


def can_use_as_hybrid_evidence(
    source: Any,
    domain: str,
    risk_level: str | None = None,
) -> bool:
    source_reference = _source_reference(source)
    source_type = _source_type(source_reference)
    trust_level = _trust_level(source_reference)

    if source_type in UNTRUSTED_SOURCE_TYPES or trust_level in UNTRUSTED_LEVELS:
        return False
    if not bool(getattr(source_reference, "allow_ai_retrieval", True)):
        return False
    if source_type not in OFFICIAL_SOURCE_TYPES | COMMUNITY_SOURCE_TYPES:
        return False
    if source_type in COMMUNITY_SOURCE_TYPES:
        moderation_status = _enum_value(getattr(source_reference, "moderation_status", None))
        return moderation_status == "approved"
    return True


def score_source_for_query(
    source: Any,
    query: str,
    base_score: float,
    domain: str,
    risk_level: str | None = None,
) -> tuple[float, list[str], list[str]]:
    source_reference = _source_reference(source)
    source_type = _source_type(source_reference)
    title = str(getattr(source_reference, "title", ""))
    content = str(
        getattr(source_reference, "content", "")
        or getattr(source, "content", "")
        or getattr(getattr(source, "chunk", None), "content", "")
        or ""
    )
    text = f"{title} {content}".casefold()
    query_terms = [term for term in query.casefold().split() if term]
    overlap_count = sum(1 for term in dict.fromkeys(query_terms) if term in text)
    boost = source_policy_boost(source_reference, domain, risk_level)
    score = float(base_score) + boost + min(overlap_count, 8) * 0.05
    reasons = [
        f"source_hierarchy_rank:{source_type_rank(source_type, _trust_level(source_reference))}",
        f"policy_boost:{boost:.2f}",
    ]

    if source_type == "official":
        reasons.append("official_source_priority")
    elif source_type == "curated_guide":
        reasons.append("curated_guide_support")
    elif source_type in COMMUNITY_SOURCE_TYPES:
        reasons.append("practical_context_only")
    if overlap_count:
        reasons.append("query_term_overlap")

    return score, reasons, source_policy_warnings(source_reference, domain, risk_level)


def _official_required_context(domain: str, risk_level: str | None) -> bool:
    return domain in SENSITIVE_DOMAINS or _normalize(risk_level) in SENSITIVE_RISK_LEVELS


def _source_reference(source: Any) -> Any:
    if hasattr(source, "chunk") and hasattr(source.chunk, "source"):
        return source.chunk.source
    if hasattr(source, "source"):
        return source.source
    return source


def _source_type(source: Any) -> str | None:
    return _enum_value(getattr(_source_reference(source), "source_type", None))


def _trust_level(source: Any) -> str | None:
    return _enum_value(getattr(_source_reference(source), "trust_level", None))


def _enum_value(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def _normalize(value: str | None) -> str:
    return (value or "").casefold()
