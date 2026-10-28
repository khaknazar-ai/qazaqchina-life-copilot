from backend.app.domain.enums import LanguageCode, RiskLevel

PROMPT_INJECTION_PATTERNS = (
    "ignore previous instructions",
    "show api key",
    "reveal secret",
    "system prompt",
    "jailbreak",
)

UNSAFE_WORK_ADVICE_PATTERNS = (
    "work on tourist visa",
    "start working first",
    "documents later",
    "безвиз",
    "туристическ",
    "потом оформ",
)

ESCALATION_RISK_LEVELS = {
    RiskLevel.legal_sensitive,
    RiskLevel.work_status_sensitive,
    RiskLevel.medical_sensitive,
    RiskLevel.emergency,
    RiskLevel.unsafe,
    RiskLevel.prompt_injection,
}

ESCALATION_SAFETY_FLAGS = {
    "prompt_injection",
    "unsafe_work_advice",
    "source_conflict",
}


def contains_prompt_injection(text: str) -> bool:
    normalized = text.casefold()
    return any(pattern in normalized for pattern in PROMPT_INJECTION_PATTERNS)


def contains_unsafe_work_advice(text: str) -> bool:
    normalized = text.casefold()
    return any(pattern in normalized for pattern in UNSAFE_WORK_ADVICE_PATTERNS)


def should_escalate(risk_level: RiskLevel, safety_flags: list[str]) -> bool:
    if risk_level in ESCALATION_RISK_LEVELS:
        return True
    return any(flag in ESCALATION_SAFETY_FLAGS for flag in safety_flags)


def default_response_language(detected_language: LanguageCode) -> LanguageCode:
    if detected_language in {
        LanguageCode.ru,
        LanguageCode.kk,
        LanguageCode.zh,
        LanguageCode.en,
    }:
        return detected_language
    return LanguageCode.ru
