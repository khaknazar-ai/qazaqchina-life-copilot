from pydantic import BaseModel, Field

from backend.app.domain.enums import LanguageCode, RiskLevel
from backend.app.memory.redaction import redact_sensitive_text
from backend.app.multilingual.detection import contains_chinese
from backend.app.multilingual.policies import needs_official_confirmation_disclaimer

CHINESE_KEY_TERMS = {
    "\u62a4\u7167": "passport",
    "\u7b7e\u8bc1": "visa",
    "\u5c45\u7559": "residence permit",
    "\u6d3e\u51fa\u6240": "police station",
    "\u533b\u9662": "hospital",
    "\u6025\u8bca": "emergency department",
    "\u5b66\u6821": "school/university",
    "\u94f6\u884c": "bank",
    "\u652f\u4ed8": "payment",
    "\u4f4f\u5bbf": "accommodation",
    "\u767b\u8bb0": "registration",
}

TERM_TRANSLATIONS = {
    "护照": ("паспорт", "төлқұжат", "护照"),
    "签证": ("виза", "виза", "签证"),
    "居留": ("проживание", "тұру", "居留"),
    "派出所": ("отделение полиции", "полиция бөлімі", "派出所"),
    "医院": ("больница", "аурухана", "医院"),
    "急诊": ("неотложная помощь", "шұғыл көмек", "急诊"),
    "学校": ("учебное заведение", "оқу орны", "学校"),
    "银行": ("банк", "банк", "银行"),
    "支付": ("оплата", "төлем", "支付"),
    "住宿": ("проживание/размещение", "орналасу", "住宿"),
    "登记": ("регистрация", "тіркеу", "登记"),
}

EXPLANATION_SUMMARIES = {
    LanguageCode.ru: (
        "Ограниченный разбор по словарю, не полный перевод. Смысл, условия и отрицания "
        "не проверены. Это не сертифицированный перевод."
    ),
    LanguageCode.kk: (
        "Сөздік бойынша шектеулі талдау, толық аударма емес. Мағынасы, шарттары мен "
        "терістеулері тексерілмеген. Бұл сертификатталған аударма емес."
    ),
    LanguageCode.zh: "这只是有限的词典匹配，不是完整翻译。语义、条件和否定尚未核实，不是认证翻译。",
    LanguageCode.en: (
        "Limited dictionary matching, not a full translation. Meaning, conditions and "
        "negations are not verified. This is not a certified translation."
    ),
}

OFFICIAL_WARNINGS = {
    LanguageCode.ru: (
        "Для важных требований подтвердите смысл у официального источника или "
        "специалиста."
    ),
    LanguageCode.kk: "Маңызды талаптарды ресми дереккөзден немесе маманнан нақтылаңыз.",
    LanguageCode.zh: "重要要求请向官方渠道或专业人士确认。",
    LanguageCode.en: "Confirm important requirements with an official source or professional.",
}

NO_CHINESE_WARNINGS = {
    LanguageCode.ru: "Текст не выглядит как китайский.",
    LanguageCode.kk: "Мәтінде қытай иероглифтері жоқ сияқты.",
    LanguageCode.zh: "文本看起来不包含中文。",
    LanguageCode.en: "Text does not appear to contain Chinese.",
}


class ChineseExplanationResult(BaseModel):
    original_text: str
    detected_language: LanguageCode
    explanation_language: LanguageCode
    summary: str
    key_terms: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    disclaimer: str


def explain_chinese_text(
    text: str,
    explanation_language: LanguageCode = LanguageCode.ru,
    risk_level: RiskLevel = RiskLevel.normal,
) -> ChineseExplanationResult:
    text = redact_sensitive_text(text)[0]
    language = _supported_explanation_language(explanation_language)
    warnings: list[str] = []
    if not contains_chinese(text):
        warnings.append(NO_CHINESE_WARNINGS[language])
    if needs_official_confirmation_disclaimer(risk_level):
        warnings.append(OFFICIAL_WARNINGS[language])

    # The excerpt identifies this input; it is visibly original text, not a
    # fabricated translation. Full original remains a separate response field.
    original_labels = {
        LanguageCode.ru: "Фрагмент оригинала", LanguageCode.kk: "Түпнұсқа үзіндісі",
        LanguageCode.zh: "原文片段", LanguageCode.en: "Original excerpt",
    }
    excerpt = text[:350] + ("…" if len(text) > 350 else "")
    return ChineseExplanationResult(
        original_text=text,
        detected_language=LanguageCode.zh if contains_chinese(text) else LanguageCode.unknown,
        explanation_language=language,
        summary=f"{EXPLANATION_SUMMARIES[language]}\n{original_labels[language]}: {excerpt}",
        key_terms=_key_terms(text, language),
        warnings=warnings,
        disclaimer=EXPLANATION_SUMMARIES[language],
    )


def _key_terms(text: str, language: LanguageCode) -> list[str]:
    languages = (LanguageCode.ru, LanguageCode.kk, LanguageCode.zh)
    index = languages.index(language) if language in languages else None
    return [
        f"{term}: {TERM_TRANSLATIONS[term][index] if index is not None else label}"
        for term, label in CHINESE_KEY_TERMS.items()
        if term in text
    ]


def _supported_explanation_language(language: LanguageCode) -> LanguageCode:
    if language in {LanguageCode.ru, LanguageCode.kk, LanguageCode.zh, LanguageCode.en}:
        return language
    return LanguageCode.ru
