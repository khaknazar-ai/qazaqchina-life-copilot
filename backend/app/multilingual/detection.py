from backend.app.domain.enums import LanguageCode

KAZAKH_SPECIFIC_LETTERS = set("әғқңөұүіһ")
ENGLISH_MARKERS = {
    "i",
    "you",
    "the",
    "and",
    "help",
    "passport",
    "student",
    "work",
    "hospital",
    "payment",
    "wechat",
    "alipay",
}


def detect_language(text: str) -> LanguageCode:
    if contains_chinese(text):
        return LanguageCode.zh
    if contains_kazakh_specific_letters(text):
        return LanguageCode.kk
    if contains_cyrillic(text):
        return LanguageCode.ru
    if contains_latin_english_markers(text):
        return LanguageCode.en
    return LanguageCode.ru


def contains_chinese(text: str) -> bool:
    return any("\u4e00" <= character <= "\u9fff" for character in text)


def contains_cyrillic(text: str) -> bool:
    return any("\u0400" <= character <= "\u04ff" for character in text)


def contains_kazakh_specific_letters(text: str) -> bool:
    lowered = text.casefold()
    return any(character in KAZAKH_SPECIFIC_LETTERS for character in lowered)


def contains_latin_english_markers(text: str) -> bool:
    normalized = text.casefold()
    latin_letters = [
        character
        for character in normalized
        if character.isascii() and character.isalpha()
    ]
    if not latin_letters:
        return False
    tokens = {
        token.strip(".,!?;:()[]")
        for token in normalized.split()
        if token.strip(".,!?;:()[]")
    }
    return bool(tokens & ENGLISH_MARKERS) or len(latin_letters) >= max(1, len(normalized) // 2)
