"""Bound recent context without replacing each message with a display preview."""

from backend.app.memory.models import ContextMessage
from backend.app.memory.redaction import redact_sensitive_text, truncate_text

MAX_CONTEXT_CHARS = 16000
MAX_CONTEXT_MESSAGES = 8
MAX_MESSAGE_CHARS = 8000


def bounded_recent_messages(
    messages: list[ContextMessage],
) -> tuple[list[ContextMessage], bool]:
    selected: list[ContextMessage] = []
    remaining = MAX_CONTEXT_CHARS
    shortened = False
    for message in reversed(messages[-MAX_CONTEXT_MESSAGES:]):
        safe_text, _ = redact_sensitive_text(message.text)
        text = truncate_text(safe_text, MAX_MESSAGE_CHARS)
        truncated = message.truncated or text != safe_text
        if len(text) > remaining:
            break
        selected.append(ContextMessage(role=message.role, text=text, truncated=truncated))
        remaining -= len(text)
        shortened |= truncated
    selected.reverse()
    # Do not send an orphan assistant reply whose question fell out of budget.
    while selected and selected[0].role != "user":
        selected.pop(0)
    return selected, shortened or len(selected) < len(messages)
