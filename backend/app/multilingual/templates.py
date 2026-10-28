from backend.app.domain.enums import LanguageCode, RiskLevel
from backend.app.multilingual.policies import needs_official_confirmation_disclaimer

RISK_DISCLAIMERS = {
    LanguageCode.ru: (
        "Важно: это не юридическая, медицинская или официальная консультация; "
        "подтвердите требования у официального источника или профильного специалиста."
    ),
    LanguageCode.kk: (
        "Маңызды: бұл заңгерлік, медициналық немесе ресми кеңес емес; "
        "талаптарды ресми дереккөзден немесе маманнан нақтылаңыз."
    ),
    LanguageCode.zh: "重要提示：这不是法律、医疗或官方意见；请向官方渠道或专业人士确认。",
    LanguageCode.en: (
        "Important: this is not legal, medical, or official advice; confirm requirements "
        "with an official source or qualified professional."
    ),
}

SOURCE_LABELS = {
    LanguageCode.ru: "Локальные источники",
    LanguageCode.kk: "Жергілікті дереккөздер",
    LanguageCode.zh: "本地来源",
    LanguageCode.en: "Selected local sources",
}

COMMUNITY_LABELS = {
    LanguageCode.ru: "Опыт сообщества: практический опыт, не официальный источник.",
    LanguageCode.kk: "Қауымдастық тәжірибесі: практикалық тәжірибе, ресми дереккөз емес.",
    LanguageCode.zh: "社区经验：这是实践经验，不是官方来源。",
    LanguageCode.en: "Community experience: practical experience, not an official source.",
}

ESCALATION_LABELS = {
    LanguageCode.ru: "Нужна проверка человеком или обращение к официальной поддержке.",
    LanguageCode.kk: "Адам тексеруі немесе ресми қолдау қажет.",
    LanguageCode.zh: "需要人工审核或联系官方支持。",
    LanguageCode.en: "Human review or official support is required.",
}


def disclaimer_for_risk(risk_level: RiskLevel, language: LanguageCode) -> str:
    if not needs_official_confirmation_disclaimer(risk_level):
        return ""
    return RISK_DISCLAIMERS[_template_language(language)]


def source_label_for_language(language: LanguageCode) -> str:
    return SOURCE_LABELS[_template_language(language)]


def community_label_for_language(language: LanguageCode) -> str:
    return COMMUNITY_LABELS[_template_language(language)]


def escalation_label_for_language(language: LanguageCode) -> str:
    return ESCALATION_LABELS[_template_language(language)]


def format_agent_answer(
    base_answer: str,
    language: LanguageCode,
    risk_level: RiskLevel,
    source_ids: list[str] | None = None,
    community_source_used: bool = False,
    escalation_required: bool = False,
) -> str:
    parts = [base_answer]
    source_ids = source_ids or []

    if source_ids:
        parts.append(f"{source_label_for_language(language)}: {', '.join(source_ids)}.")
    if community_source_used:
        parts.append(community_label_for_language(language))
    disclaimer = disclaimer_for_risk(risk_level, language)
    if disclaimer:
        parts.append(disclaimer)
    if escalation_required:
        parts.append(escalation_label_for_language(language))

    return " ".join(part for part in parts if part)


def _template_language(language: LanguageCode) -> LanguageCode:
    if language in {LanguageCode.ru, LanguageCode.kk, LanguageCode.zh, LanguageCode.en}:
        return language
    return LanguageCode.ru
