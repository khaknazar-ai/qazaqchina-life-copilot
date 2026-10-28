"""Short-lived, bounded server answers for saving a conversation to an owned case."""

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass

from fastapi import HTTPException
from pydantic import Field

from backend.app.schemas.chat import ChatResponse
from backend.app.workspace.models import StrictModel
from backend.app.workspace.service import clean_text, sanitize_response


class AttachTurnRequest(StrictModel):
    trace_id: str = Field(min_length=1, max_length=128)


@dataclass(frozen=True)
class ServerTurn:
    owner: str
    message: str
    response: ChatResponse
    expires: float
    city: str | None = None


class ServerTurnStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._turns: OrderedDict[str, ServerTurn] = OrderedDict()

    def remember(
        self, owner: str, message: str, response: ChatResponse, *, city: str | None = None,
    ) -> None:
        # Keep the sanitized exchange for owner-scoped attachment.
        # Raw provider payloads are excluded.
        minimal = sanitize_response(response, case_id=response.case_id)
        with self._lock:
            self._expire()
            self._turns[response.trace_id] = ServerTurn(
                owner,
                clean_text(message),
                minimal,
                time.monotonic() + 3600,
                clean_text(city)[:100] if city else None,
            )
            while len(self._turns) > 200:
                self._turns.popitem(last=False)

    def get(self, owner: str, trace_id: str) -> ServerTurn:
        with self._lock:
            self._expire()
            turn = self._turns.get(trace_id)
            if turn is None or turn.owner != owner:
                raise HTTPException(404, "chat_turn_not_found_or_expired")
            return turn

    def _expire(self):
        current = time.monotonic()
        for key in [key for key, turn in self._turns.items() if turn.expires <= current]:
            del self._turns[key]
