import re
from datetime import date

from backend.app.memory.models import MemoryRetentionPolicy
from backend.app.privacy.patterns import (
    ADDRESS_PATTERNS,
    LABELED_ID_PATTERN,
    LABELED_PHONE_PATTERN,
    PRIVATE_CONTACT_PATTERN,
    SECRET_PATTERNS,
)

EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_PATTERN = re.compile(r"(?:\+?\d{1,3}[\s().-]*)?(?:\d[\s().-]*){7,}\d")
ISO_DATE_PATTERN = re.compile(r"(?<![\d-])\d{4}-\d{2}-\d{2}(?![\d-])")
CURRENCY_AMOUNT_PATTERN = re.compile(
    r"(?<![\dA-Za-z_+])(?:[$¥￥€₸]\s*\d{1,12}(?:\.\d{1,2})?(?![\d.])|"
    r"\d{1,12}(?:\.\d{1,2})?\s*(?:CNY|RMB|USD|EUR|KZT|元|人民币|теңге|тенге|"
    r"yuan|dollars?|euros?|юан(?:ь|я|ей|ях|ями)|доллар(?:ов|а)?|евро)"
    r"(?![A-Za-z0-9_]))",
    re.I,
)
CURRENCY_LABELED_ID_PATTERN = re.compile(
    r"\b(?:id|national[_ -]?id)\b\s*[:：=#]?\s*" + CURRENCY_AMOUNT_PATTERN.pattern, re.I
)
LONG_NUMBER_PATTERN = re.compile(r"\b\d{8,}\b")
PASSPORT_OR_ID_PATTERN = re.compile(
    r"\b(?=[A-Z0-9-]{8,}\b)(?=[A-Z0-9-]*[A-Z])(?=[A-Z0-9-]*\d)[A-Z0-9-]+\b",
    re.I,
)


def redact_sensitive_text(text: str) -> tuple[str, list[str]]:
    redacted = str(text or "")
    warnings: list[str] = []

    redacted, secret_warnings = _replace_patterns(
        redacted,
        SECRET_PATTERNS,
        "[REDACTED_SECRET]",
        "secret_like_value_redacted",
    )
    warnings.extend(secret_warnings)

    redacted, email_warnings = _replace_pattern(
        redacted,
        EMAIL_PATTERN,
        "[REDACTED_EMAIL]",
        "email_redacted",
    )
    warnings.extend(email_warnings)

    redacted, address_warnings = _replace_patterns(
        redacted,
        ADDRESS_PATTERNS,
        "[REDACTED_ADDRESS]",
        "address_like_value_redacted",
    )
    warnings.extend(address_warnings)

    redacted, id_warnings = _replace_id_values(redacted)
    warnings.extend(id_warnings)

    redacted, labeled_warnings = _replace_patterns(
        redacted,
        [LABELED_ID_PATTERN, LABELED_PHONE_PATTERN, CURRENCY_LABELED_ID_PATTERN,
         PRIVATE_CONTACT_PATTERN],
        "[REDACTED_PRIVATE]", "private_identifier_redacted",
    )
    warnings.extend(labeled_warnings)

    # Explicit monetary units distinguish an amount from a bare identifier.
    # Secret, address and labeled-ID redaction has already run and remains final.
    parts: list[str] = []
    start = 0
    for match in CURRENCY_AMOUNT_PATTERN.finditer(redacted):
        value, numeric_warnings = _replace_numeric_values(redacted[start : match.start()])
        parts.extend((value, match.group()))
        warnings.extend(numeric_warnings)
        start = match.end()
    value, numeric_warnings = _replace_numeric_values(redacted[start:])
    parts.append(value)
    warnings.extend(numeric_warnings)
    redacted = "".join(parts)

    return redacted, list(dict.fromkeys(warnings))


def truncate_text(text: str, max_chars: int) -> str:
    value = str(text or "")
    if max_chars <= 0:
        return ""
    if len(value) <= max_chars:
        return value
    suffix = "... [truncated]"
    if max_chars <= len(suffix):
        return value[:max_chars]
    return f"{value[: max_chars - len(suffix)].rstrip()}{suffix}"


def sanitize_turn_text(
    text: str,
    policy: MemoryRetentionPolicy,
) -> tuple[str, list[str]]:
    value = "" if not policy.persist_raw_messages else str(text or "")
    warnings: list[str] = []
    if not policy.persist_raw_messages:
        value = str(text or "")
    if policy.redact_sensitive_data:
        value, warnings = redact_sensitive_text(value)
    truncated = truncate_text(value, policy.max_text_chars)
    if truncated != value:
        warnings.append("text_truncated")
    return truncated, list(dict.fromkeys(warnings))


def _replace_patterns(
    text: str,
    patterns: list[re.Pattern],
    replacement: str,
    warning: str,
) -> tuple[str, list[str]]:
    value = text
    warnings: list[str] = []
    for pattern in patterns:
        value, pattern_warnings = _replace_pattern(value, pattern, replacement, warning)
        warnings.extend(pattern_warnings)
    return value, warnings


def _replace_pattern(
    text: str,
    pattern: re.Pattern,
    replacement: str,
    warning: str,
) -> tuple[str, list[str]]:
    if pattern.search(text):
        return pattern.sub(replacement, text), [warning]
    return text, []


def _replace_phone_values(text: str) -> tuple[str, list[str]]:
    warnings: list[str] = []

    def replace(match: re.Match) -> str:
        digits = "".join(character for character in match.group(0) if character.isdigit())
        if len(digits) < 8:
            return match.group(0)
        warnings.append("phone_like_value_redacted")
        return "[REDACTED_PHONE]"

    # A date followed by a time can be one broad phone-pattern match. Split at
    # validated calendar dates so document deadlines survive without exempting
    # arbitrary dashed numbers or nearby telephone values.
    parts: list[str] = []
    start = 0
    for match in ISO_DATE_PATTERN.finditer(text):
        try:
            date.fromisoformat(match.group())
        except ValueError:
            continue
        parts.append(PHONE_PATTERN.sub(replace, text[start : match.start()]))
        parts.append(match.group())
        start = match.end()
    parts.append(PHONE_PATTERN.sub(replace, text[start:]))
    return "".join(parts), list(dict.fromkeys(warnings))


def _replace_numeric_values(text: str) -> tuple[str, list[str]]:
    value, warnings = _replace_pattern(
        text, LONG_NUMBER_PATTERN, "[REDACTED_NUMBER]", "long_number_redacted"
    )
    value, phone_warnings = _replace_phone_values(value)
    return value, [*warnings, *phone_warnings]


def _replace_id_values(text: str) -> tuple[str, list[str]]:
    # Unit-adjacent amounts (for example 10000000CNY) are not alphanumeric IDs.
    # Labeled IDs/phones still run over the full text afterwards, so an explicit
    # private field is not exempted just because a currency unit follows it.
    parts: list[str] = []
    warnings: list[str] = []
    start = 0
    for match in CURRENCY_AMOUNT_PATTERN.finditer(text):
        value, found = _replace_pattern(
            text[start : match.start()], PASSPORT_OR_ID_PATTERN,
            "[REDACTED_ID]", "id_like_value_redacted",
        )
        parts.extend((value, match.group()))
        warnings.extend(found)
        start = match.end()
    value, found = _replace_pattern(
        text[start:], PASSPORT_OR_ID_PATTERN, "[REDACTED_ID]", "id_like_value_redacted",
    )
    parts.append(value)
    return "".join(parts), list(dict.fromkeys([*warnings, *found]))
