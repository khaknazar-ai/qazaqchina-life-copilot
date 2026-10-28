"""Minimal transport contract used by the existing verified answer pipeline."""

from typing import Protocol


class StructuredChatClient(Protocol):
    def complete(self, messages: list[dict], *, kind: str) -> tuple[str, dict]: ...
