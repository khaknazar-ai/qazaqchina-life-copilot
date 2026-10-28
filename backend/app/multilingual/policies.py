from backend.app.domain.enums import LanguageCode, RiskLevel

SUPPORTED_RESPONSE_LANGUAGES = [
    LanguageCode.ru,
    LanguageCode.kk,
    LanguageCode.zh,
    LanguageCode.en,
]

OFFICIAL_CONFIRMATION_RISK_LEVELS = {
    RiskLevel.legal_sensitive,
    RiskLevel.work_status_sensitive,
    RiskLevel.medical_sensitive,
    RiskLevel.emergency,
}


def choose_response_language(
    detected_language: LanguageCode | None,
    preferred_language: LanguageCode | None = None,
) -> LanguageCode:
    if preferred_language in SUPPORTED_RESPONSE_LANGUAGES:
        return preferred_language
    if detected_language in SUPPORTED_RESPONSE_LANGUAGES:
        return detected_language
    return LanguageCode.ru


def language_label(language: LanguageCode) -> str:
    return {
        LanguageCode.ru: "Russian",
        LanguageCode.kk: "Kazakh",
        LanguageCode.zh: "Chinese",
        LanguageCode.en: "English",
        LanguageCode.unknown: "Unknown",
    }[language]


def needs_translation_disclaimer(risk_level: RiskLevel) -> bool:
    return risk_level in {
        RiskLevel.legal_sensitive,
        RiskLevel.work_status_sensitive,
        RiskLevel.medical_sensitive,
        RiskLevel.emergency,
        RiskLevel.medium,
    }


def needs_official_confirmation_disclaimer(risk_level: RiskLevel) -> bool:
    return risk_level in OFFICIAL_CONFIRMATION_RISK_LEVELS


def supported_response_languages() -> list[LanguageCode]:
    return list(SUPPORTED_RESPONSE_LANGUAGES)
