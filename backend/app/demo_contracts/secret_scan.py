"""Heuristic static checks for embedded credentials, not authentication syntax."""

import re

SECRET_PATTERNS = {
    "provider_key": re.compile(r"\b(?:sk|dk|rk|pk)-[A-Za-z0-9_-]{8,}", re.I),
    "provider_secret_setting": re.compile(
        r"\b(?:openai|deepseek|openrouter|dashscope)_api_key\b", re.I,
    ),
    "literal_bearer_value": re.compile(r"\bbearer\s+[A-Za-z0-9_.=-]{8,}", re.I),
    "literal_key_assignment": re.compile(
        r"\b(?:api[_ -]?key|pilotAccessToken|accessToken)\b[\"']?\s*[:=]\s*"
        r"[\"'`][A-Za-z0-9_.=-]{8,}", re.I,
    ),
}


def frontend_secret_markers(text: str) -> list[str]:
    # Never include the matched value in findings or reports.
    return [label for label, pattern in SECRET_PATTERNS.items() if pattern.search(text)]
