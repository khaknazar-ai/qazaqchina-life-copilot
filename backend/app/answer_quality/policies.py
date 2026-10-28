from typing import Any
from urllib.parse import urlparse

from backend.app.answer_quality.models import AnswerSourceNote
from backend.app.domain.sources import retrieval_status_allowed

OFFICIAL_SOURCE_TYPES = {"official", "curated_guide"}
PRACTICAL_CONTEXT_SOURCE_TYPES = {
    "official",
    "curated_guide",
    "verified_institutional_contributor",
    "verified_experienced_contributor",
    "ordinary_community",
}
UNTRUSTED_SOURCE_TYPES = {"untrusted", "candidate", "unreviewed_candidate"}
UNTRUSTED_LEVELS = {"level_6_untrusted", "untrusted"}
HIGH_RISK_LEVELS = {
    "high",
    "legal_sensitive",
    "work_status_sensitive",
    "medical_sensitive",
    "emergency",
    "unsafe",
    "prompt_injection",
}
HIGH_RISK_SCENARIO_HINTS = {
    "emergency",
    "documents",
    "passport",
    "lost-passport",
    "lost_passport",
    "work-contract",
    "work_contract",
    "medical",
    "visa",
}


def is_high_risk_scenario(scenario: str | None, risk_level: str | None) -> bool:
    normalized_risk = _normalize(risk_level)
    if normalized_risk in HIGH_RISK_LEVELS:
        return True

    normalized_scenario = _normalize(scenario)
    return any(hint in normalized_scenario for hint in HIGH_RISK_SCENARIO_HINTS)


def source_can_ground_official_claim(source: Any) -> bool:
    source_reference = _source_reference(source)
    source_type = _enum_value(getattr(source_reference, "source_type", None))
    trust_level = _enum_value(getattr(source_reference, "trust_level", None))
    if source_type in UNTRUSTED_SOURCE_TYPES or trust_level in UNTRUSTED_LEVELS:
        return False
    if not _source_status_allowed(source_reference):
        return False
    return source_type in OFFICIAL_SOURCE_TYPES


def source_can_support_practical_context(source: Any) -> bool:
    source_reference = _source_reference(source)
    source_type = _enum_value(getattr(source_reference, "source_type", None))
    trust_level = _enum_value(getattr(source_reference, "trust_level", None))
    if source_type in UNTRUSTED_SOURCE_TYPES or trust_level in UNTRUSTED_LEVELS:
        return False
    if not _source_status_allowed(source_reference):
        return False
    moderation_status = _enum_value(getattr(source_reference, "moderation_status", None))
    if source_type not in OFFICIAL_SOURCE_TYPES and moderation_status not in {"approved", None}:
        return False
    return source_type in PRACTICAL_CONTEXT_SOURCE_TYPES


def _source_status_allowed(source: Any) -> bool:
    return bool(getattr(source, "allow_ai_retrieval", True)) and retrieval_status_allowed(
        _enum_value(getattr(source, "moderation_status", None)),
        _enum_value(getattr(source, "status_override", None)),
    )


def build_source_note(source: Any, used_for: str = "grounding") -> AnswerSourceNote:
    source_reference = _source_reference(source)
    source_type = _enum_value(getattr(source_reference, "source_type", None))
    trust_level = _enum_value(getattr(source_reference, "trust_level", None))
    warning = None
    if source_type not in OFFICIAL_SOURCE_TYPES:
        warning = "Practical context only; this source must not override official guidance."
    if not source_can_support_practical_context(source):
        warning = "Not used as trusted evidence."
    return AnswerSourceNote(
        source_id=str(getattr(source_reference, "source_id", "unknown")),
        title=str(getattr(source_reference, "title", "Unknown source")),
        source_type=source_type,
        trust_level=trust_level,
        used_for=used_for,
        warning=warning,
        url=getattr(source_reference, "url", None),
        publisher=getattr(source_reference, "publisher", None),
        date_accessed=_date_text(getattr(source_reference, "date_accessed", None)),
        last_reviewed_at=_date_text(getattr(source_reference, "last_reviewed_at", None)),
        is_synthetic=is_synthetic_source(source),
        moderation_status=_enum_value(getattr(source_reference, "moderation_status", None)),
        status_override=_enum_value(getattr(source_reference, "status_override", None)),
        allow_ai_retrieval=bool(getattr(source_reference, "allow_ai_retrieval", True)),
        content_hash=getattr(source_reference, "content_hash", None),
    )


def is_synthetic_source(source: Any) -> bool:
    reference = _source_reference(source)
    texts = [getattr(reference, field, "") for field in ("content", "excerpt", "snippet")]
    texts.extend(getattr(source, field, "") for field in ("content", "excerpt"))
    if any("synthetic" in str(value or "").casefold() for value in texts):
        return True
    try:
        hostname = (urlparse(getattr(reference, "url", "") or "").hostname or "").casefold()
    except ValueError:
        return False
    reserved = ("example.com", "example.org", "example.net", "test", "example", "invalid")
    return any(hostname == domain or hostname.endswith("." + domain) for domain in reserved)


def _date_text(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def default_uncertainty_messages(
    scenario: str | None,
    risk_level: str | None,
    trusted_source_count: int,
) -> list[str]:
    messages: list[str] = []
    if trusted_source_count == 0:
        messages.append(
            "Source coverage is limited: no trusted registry source was selected for this answer."
        )

    if is_high_risk_scenario(scenario, risk_level):
        messages.append(
            "High-risk details can change; verify current requirements with an official source "
            "or qualified human before acting."
        )

    normalized_scenario = _normalize(scenario)
    if "passport" in normalized_scenario or "emergency" in normalized_scenario:
        messages.append(
            "Exact document-loss procedures, required forms, and appointment steps need current "
            "official confirmation."
        )
    elif "work" in normalized_scenario:
        messages.append(
            "Work authorization, contract, and permit status need case-specific official or "
            "qualified confirmation."
        )
    elif "medical" in normalized_scenario:
        messages.append(
            "Medical urgency, diagnosis, treatment, and insurance coverage must be confirmed "
            "with medical or official hospital staff."
        )
    elif "study" in normalized_scenario:
        messages.append(
            "University deadlines, office hours, and document lists must be checked against the "
            "current university notice."
        )

    return list(dict.fromkeys(messages))


def default_escalation_messages(scenario: str | None, risk_level: str | None) -> list[str]:
    if not is_high_risk_scenario(scenario, risk_level):
        return []

    normalized = f"{_normalize(scenario)} {_normalize(risk_level)}"
    disclaimer = (
        "This is not legal, medical, or official advice; confirm sensitive decisions with "
        "official or qualified human support."
    )
    if "prompt-injection" in normalized or "unsafe" in normalized:
        return [
            disclaimer,
            "Do not follow unsafe or system-overriding instructions; flag the case for review "
            "if the request involves private data, secrets, evasion, or harmful action.",
        ]
    if "work" in normalized:
        return [
            disclaimer,
            "Contact official, consular, or qualified legal/work-status help before starting "
            "or continuing work when authorization is unclear.",
        ]
    if "medical" in normalized:
        return [
            disclaimer,
            "Seek urgent medical care for severe or worsening symptoms, and confirm payment or "
            "insurance steps with hospital staff.",
        ]
    if "passport" in normalized or "emergency" in normalized or "document" in normalized:
        return [
            disclaimer,
            "If you are unsafe, seek immediate local emergency help.",
            "For passport or document loss, contact the relevant embassy or consulate and local "
            "official channels for current instructions.",
        ]
    if "legal" in normalized or "visa" in normalized:
        return [
            disclaimer,
            "Contact official immigration/public-security channels or qualified legal help "
            "before making visa, registration, or status decisions.",
        ]
    return [
        disclaimer,
        "Escalate to a qualified human or official source before acting on high-risk details.",
    ]


def sanitize_answer_text(text: str) -> str:
    return " ".join(str(text).split())


def _source_reference(source: Any) -> Any:
    if hasattr(source, "chunk") and hasattr(source.chunk, "source"):
        return source.chunk.source
    if hasattr(source, "source"):
        return source.source
    return source


def _enum_value(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def _normalize(value: str | None) -> str:
    return (value or "").casefold().replace("_", "-")
