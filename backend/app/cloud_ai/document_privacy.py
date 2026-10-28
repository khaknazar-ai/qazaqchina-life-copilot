"""Preserve source-equal dates and amounts without exempting private identifiers."""

import re

from backend.app.cloud_ai.document_numbers import protected_detail_spans
from backend.app.memory.redaction import (
    CURRENCY_LABELED_ID_PATTERN,
    EMAIL_PATTERN,
    redact_sensitive_text,
)
from backend.app.privacy.patterns import (
    ADDRESS_PATTERNS,
    LABELED_ID_PATTERN,
    LABELED_PHONE_PATTERN,
    PRIVATE_CONTACT_PATTERN,
    SECRET_PATTERNS,
)

EXPLICIT_PRIVATE_PATTERNS = [
    *SECRET_PATTERNS, *ADDRESS_PATTERNS, EMAIL_PATTERN, LABELED_ID_PATTERN,
    LABELED_PHONE_PATTERN, PRIVATE_CONTACT_PATTERN, CURRENCY_LABELED_ID_PATTERN,
    re.compile(
        r"(?i)(?:\b(?:id|national[_ -]?id|passport|паспорт(?:а)?|төлқұжат|iin|иин|жсн|"
        r"phone|telephone|mobile|телефон)\b|护照号|身份证号|电话|手机号)"
        r"\s*(?:number|номер|нөмірі|№|no\.?)?\s*[:：=#]?"
        r"[\s\"'“”‘’«»()\[\]{}<>]*[+\-−]?\d"
    ),
]


def has_private_document_output(original: str, text: str, *, language: str) -> bool:
    # A date/amount in a labeled private field must not acquire a numeric exemption.
    if any(pattern.search(text) for pattern in EXPLICIT_PRIVATE_PATTERNS):
        return True
    masked = text
    for start, end in sorted(protected_detail_spans(original, text, language=language),
                             reverse=True):
        masked = masked[:start] + "[DOCUMENT_DETAIL]" + masked[end:]
    return bool(redact_sensitive_text(masked)[1])
