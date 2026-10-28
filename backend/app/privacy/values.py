"""Redact private text in nested support and diagnostic payloads."""

import re
from typing import Any

_PRIVATE_KEYS = (
    "password", "api_key", "apikey", "token", "secret", "authorization",
    "passport", "phone", "email", "address", "identity_number", "national_id",
)
_REFERENCE_KEYS = {
    "trace_id", "case_id", "source_id", "source_ids", "citation_id", "citation_ids",
    "session_id", "user_id", "actor_id", "related_turn_id", "workspace_ticket_id",
    "selected_source_ids", "blocked_conflict_ids", "conflict_id", "conflict_ids", "snapshot_id",
}
_REFERENCE = re.compile(r"[A-Za-z0-9_.:-]{1,128}")


def redact_private_value(
    value: Any, *, preserve_references: bool = False, key: str = "",
) -> Any:
    if isinstance(value, dict):
        if preserve_references and key == "snapshot_refs":
            return {
                redact_private_value(name, preserve_references=True, key="source_id"):
                redact_private_value(item, preserve_references=True, key="snapshot_id")
                for name, item in value.items()
            }
        return {
            redact_private_value(name): (
                "[REDACTED]"
                if any(part in name.casefold() for part in _PRIVATE_KEYS)
                else redact_private_value(
                    item, preserve_references=preserve_references, key=name,
                )
            )
            for name, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [
            redact_private_value(item, preserve_references=preserve_references, key=key)
            for item in value
        ]
    if isinstance(value, str):
        # Lazy import avoids a cycle through the memory/privacy package exports.
        from backend.app.memory.redaction import redact_sensitive_text

        redacted, warnings = redact_sensitive_text(value)
        if (
            preserve_references and key in _REFERENCE_KEYS and _REFERENCE.fullmatch(value)
            and set(warnings) <= {"id_like_value_redacted", "long_number_redacted"}
        ):
            return value
        return redacted
    if isinstance(value, int) and not isinstance(value, bool) and len(str(abs(value))) >= 8:
        return "[REDACTED_NUMBER]"
    if isinstance(value, float) and value.is_integer() and len(str(abs(int(value)))) >= 8:
        return "[REDACTED_NUMBER]"
    return value
