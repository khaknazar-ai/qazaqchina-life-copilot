import re
from dataclasses import dataclass
from typing import Any

from backend.app.durable_storage.models import RAW_IMAGE_METADATA_KEYS
from backend.app.privacy.models import PIIDetection, RedactionResult
from backend.app.privacy.patterns import (
    ADDRESS_PATTERNS,
    LABELED_ID_PATTERN,
    PRIVATE_CONTACT_PATTERN,
    SECRET_PATTERNS,
)
from backend.app.privacy.values import redact_private_value

SENSITIVE_METADATA_KEYS = {
    *RAW_IMAGE_METADATA_KEYS,
    "api_key",
    "apikey",
    "secret",
    "token",
    "authorization",
    "password",
}

PHONE_PATTERN = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)")
EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PASSPORT_PATTERN = re.compile(r"\b[A-Z]{1,2}\d{6,9}\b", re.IGNORECASE)
NATIONAL_ID_PATTERN = re.compile(r"\b\d{12}\b")
BANK_CARD_PATTERN = re.compile(r"\b(?:\d[ -]?){13,19}\b")
SECRET_PATTERN = re.compile(r"\b(?:sk|dk|rk|pk|xoxb|xoxp)-[A-Za-z0-9_=-]{8,}\b")
ADDRESS_HINT_PATTERN = re.compile(
    r"\b(?:address|адрес|мекенжай|住所|地址|street|road|building|apartment)\b",
    re.IGNORECASE,
)
MEDICAL_HINT_PATTERN = re.compile(
    r"\b(?:medical|hospital|diagnosis|patient|clinic|болезн|врач|аурухана|医院|病历)\b",
    re.IGNORECASE,
)
VISA_HINT_PATTERN = re.compile(
    r"\b(?:visa|passport|residence permit|overstay|виза|паспорт|签证|护照|居留)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class _Rule:
    category: str
    pattern: re.Pattern[str]
    replacement: str
    warning: str


REDACTION_RULES = [
    *[
        _Rule("address_value", pattern, "[REDACTED_ADDRESS]", "Address value detected.")
        for pattern in ADDRESS_PATTERNS
    ],
    *[
        _Rule("api_key_or_secret_like", pattern, "[REDACTED_SECRET]", "Secret detected.")
        for pattern in SECRET_PATTERNS
    ],
    _Rule("passport_like_id", LABELED_ID_PATTERN, "[REDACTED_ID]", "Labeled ID detected."),
    _Rule(
        "private_contact", PRIVATE_CONTACT_PATTERN,
        "[REDACTED_CONTACT]", "Private contact detected.",
    ),
    _Rule(
        "api_key_or_secret_like",
        SECRET_PATTERN,
        "[REDACTED_SECRET]",
        "Secret-like values are detected heuristically and must not be stored.",
    ),
    _Rule("email", EMAIL_PATTERN, "[REDACTED_EMAIL]", "Email address detected."),
    _Rule("bank_card_like", BANK_CARD_PATTERN, "[REDACTED_CARD]", "Card-like number detected."),
    _Rule(
        "passport_like_id",
        PASSPORT_PATTERN,
        "[REDACTED_ID]",
        "Passport-like identifier detected.",
    ),
    _Rule(
        "national_id_like",
        NATIONAL_ID_PATTERN,
        "[REDACTED_ID]",
        "National-ID-like number detected.",
    ),
    _Rule("phone_number", PHONE_PATTERN, "[REDACTED_PHONE]", "Phone-like number detected."),
    _Rule("address_hint", ADDRESS_HINT_PATTERN, "[REDACTED_SENSITIVE]", "Address hint detected."),
    _Rule("medical_hint", MEDICAL_HINT_PATTERN, "[REDACTED_SENSITIVE]", "Medical hint detected."),
    _Rule("visa_hint", VISA_HINT_PATTERN, "[REDACTED_SENSITIVE]", "Visa/passport hint detected."),
]


def detect_pii(text: str) -> list[PIIDetection]:
    detections: list[PIIDetection] = []
    for rule in REDACTION_RULES:
        for match in rule.pattern.finditer(text or ""):
            detections.append(
                PIIDetection(
                    category=rule.category,
                    matched=None,
                    start=match.start(),
                    end=match.end(),
                    confidence="heuristic",
                    warning=rule.warning,
                )
            )
    return sorted(detections, key=lambda item: (item.start or 0, item.end or 0, item.category))


def redact_pii(text: str) -> RedactionResult:
    source = text or ""
    matches = _non_overlapping_matches(source)
    redacted = _replace_matches(source, matches)
    detections = [
        PIIDetection(
            category=rule.category,
            matched=None,
            start=start,
            end=end,
            confidence="heuristic",
            warning=rule.warning,
        )
        for start, end, rule in matches
    ]
    warnings = []
    if detections:
        warnings.append("PII detection is heuristic and can include false positives or misses.")
    return RedactionResult(
        original_contains_pii=bool(detections),
        redacted_text=redacted,
        detections=detections,
        warnings=warnings,
    )


def sanitize_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return _sanitize_value(metadata, path="metadata")


def _sanitize_value(value: Any, path: str) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, nested_value in value.items():
            normalized = str(key).casefold()
            if normalized in SENSITIVE_METADATA_KEYS:
                sanitized[key] = "[REDACTED_SECRET]"
                continue
            safe_key = redact_private_value(str(key))
            sanitized[safe_key] = _sanitize_value(nested_value, f"{path}.{key}")
        return sanitized
    if isinstance(value, (list, tuple)):
        return [_sanitize_value(item, f"{path}[]") for item in value]
    if isinstance(value, str):
        return redact_pii(value).redacted_text
    return redact_private_value(value)


def _non_overlapping_matches(text: str) -> list[tuple[int, int, _Rule]]:
    matches: list[tuple[int, int, _Rule]] = []
    for rule in REDACTION_RULES:
        for match in rule.pattern.finditer(text):
            matches.append((match.start(), match.end(), rule))
    matches.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    accepted: list[tuple[int, int, _Rule]] = []
    occupied: list[tuple[int, int]] = []
    for start, end, rule in matches:
        overlaps_existing = any(
            start < existing_end and end > existing_start
            for existing_start, existing_end in occupied
        )
        if overlaps_existing:
            continue
        accepted.append((start, end, rule))
        occupied.append((start, end))
    return sorted(accepted, key=lambda item: item[0])


def _replace_matches(text: str, matches: list[tuple[int, int, _Rule]]) -> str:
    if not matches:
        return text
    chunks: list[str] = []
    cursor = 0
    for start, end, rule in matches:
        chunks.append(text[cursor:start])
        chunks.append(rule.replacement)
        cursor = end
    chunks.append(text[cursor:])
    return "".join(chunks)
