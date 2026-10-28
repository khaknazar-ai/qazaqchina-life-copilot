from threading import RLock
from typing import Any

from pydantic import ValidationError

from backend.app.memory.context import (
    build_followup_context,
    update_memory_from_agent_result,
)
from backend.app.memory.models import (
    ConversationTurn,
    FollowUpContext,
    MemoryRetentionPolicy,
    SessionMemory,
    utc_now,
)
from backend.app.memory.redaction import redact_sensitive_text, sanitize_turn_text
from backend.app.persistence.base import RecordStoreProtocol

SESSION_MEMORY_RECORD_TYPE = "session_memory"
SESSION_RESET_RECORD_TYPE = "session_memory_reset"


class SessionMemoryService:
    def __init__(
        self,
        repository: RecordStoreProtocol | None = None,
        retention_policy: MemoryRetentionPolicy | None = None,
    ) -> None:
        self.repository = repository
        self.retention_policy = retention_policy or MemoryRetentionPolicy()
        self._sessions: dict[str, SessionMemory] = {}
        self._state_lock = RLock()
        self._session_locks: dict[str, RLock] = {}
        self._load_sessions()

    def _session_lock(self, session_id: str) -> RLock:
        normalized_id = _normalize_session_id(session_id)
        with self._state_lock:
            return self._session_locks.setdefault(normalized_id, RLock())

    def get_or_create_session(self, session_id: str) -> SessionMemory:
        normalized_id = _normalize_session_id(session_id)
        with self._session_lock(normalized_id), self._state_lock:
            existing = self._sessions.get(normalized_id)
            if existing is not None:
                return existing
            memory = SessionMemory(
                session_id=normalized_id,
                retention_policy=self.retention_policy,
            )
            self._sessions[normalized_id] = memory
            return memory

    def save_session(self, memory: SessionMemory) -> SessionMemory:
        with self._session_lock(memory.session_id):
            updated = memory.model_copy(update={"updated_at": utc_now()}, deep=True)
            _sanitize_city(updated)
            updated.recent_turns = updated.recent_turns[-updated.retention_policy.max_turns :]
            if self.repository is not None:
                self.repository.append(
                    record_type=SESSION_MEMORY_RECORD_TYPE,
                    payload=updated.model_dump(mode="json"),
                    record_id=updated.session_id,
                )
            with self._state_lock:
                self._sessions[updated.session_id] = updated
            return updated

    def add_turn(
        self,
        session_id: str,
        role: str,
        text: str,
        scenario: str | None = None,
        risk_level: str | None = None,
        language: str | None = None,
        metadata: dict | None = None,
    ) -> SessionMemory:
        with self._session_lock(session_id):
            memory = self.get_or_create_session(session_id)
            sanitized_text, warnings = sanitize_turn_text(text, memory.retention_policy)
            turn = ConversationTurn(
                role=role,
                text=sanitized_text,
                scenario=scenario,
                risk_level=risk_level,
                language=language,
                redacted=bool(warnings) or memory.retention_policy.redact_sensitive_data,
                metadata=_metadata_with_warnings(metadata or {}, warnings),
            )
            updated = memory.model_copy(deep=True)
            updated.recent_turns.append(turn)
            updated.recent_turns = updated.recent_turns[-updated.retention_policy.max_turns :]
            updated.active_scenario = scenario or updated.active_scenario
            updated.active_risk_level = risk_level or updated.active_risk_level
            updated.preferred_language = language or updated.preferred_language
            updated.safety_warnings = list(dict.fromkeys([*updated.safety_warnings, *warnings]))
            return self.save_session(updated)

    def update_from_agent_result(
        self,
        session_id: str,
        result: Any,
        user_message: str | None = None,
    ) -> SessionMemory:
        with self._session_lock(session_id):
            memory = self.get_or_create_session(session_id)
            updated = update_memory_from_agent_result(memory, result, user_message=user_message)
            return self.save_session(updated)

    def set_city(self, session_id: str, city: str, *, only_if_empty: bool = False) -> SessionMemory:
        with self._session_lock(session_id):
            memory = self.get_or_create_session(session_id)
            if only_if_empty and memory.city:
                return memory
            return self.save_session(memory.model_copy(update={"city": city}, deep=True))

    def build_context(self, session_id: str) -> FollowUpContext:
        with self._session_lock(session_id):
            return build_followup_context(self.get_or_create_session(session_id))

    def clear_session(self, session_id: str) -> bool:
        normalized_id = _normalize_session_id(session_id)
        with self._session_lock(normalized_id):
            with self._state_lock:
                existed = normalized_id in self._sessions
            if existed and self.repository is not None:
                self.repository.append(
                    record_type=SESSION_RESET_RECORD_TYPE,
                    payload={"session_id": normalized_id},
                    record_id=normalized_id,
                )
            with self._state_lock:
                self._sessions.pop(normalized_id, None)
            return existed

    def list_sessions(self) -> list[SessionMemory]:
        with self._state_lock:
            return [memory.model_copy(deep=True) for memory in self._sessions.values()]

    def _load_sessions(self) -> None:
        if self.repository is None:
            return
        latest: dict[str, SessionMemory] = {}
        for record in self.repository.list_records():
            if record.record_type == SESSION_RESET_RECORD_TYPE:
                latest.pop(str(record.payload.get("session_id", "")), None)
                continue
            if record.record_type != SESSION_MEMORY_RECORD_TYPE:
                continue
            try:
                memory = SessionMemory.model_validate(record.payload)
            except (ValidationError, TypeError, ValueError):
                continue
            _sanitize_city(memory)
            latest[memory.session_id] = memory
        self._sessions = latest


def _sanitize_city(memory: SessionMemory) -> None:
    if memory.city:
        _sanitized, warnings = redact_sensitive_text(memory.city)
        if warnings:
            # A contact, document number, or street address is not a city filter.
            memory.city = None
            memory.safety_warnings = list(
                dict.fromkeys(
                    [
                        *memory.safety_warnings,
                        "sensitive_city_field_removed",
                    ]
                )
            )


def _metadata_with_warnings(metadata: dict, warnings: list[str]) -> dict:
    safe_metadata = {
        str(key): _safe_metadata_value(value)
        for key, value in metadata.items()
        if key != "raw_text"
    }
    safe_metadata["redaction_warnings"] = list(dict.fromkeys(warnings))
    return safe_metadata


def _safe_metadata_value(value: Any) -> Any:
    if isinstance(value, str):
        sanitized, _warnings = sanitize_turn_text(value, MemoryRetentionPolicy())
        return sanitized
    return value


def _normalize_session_id(session_id: str) -> str:
    normalized = str(session_id or "").strip()
    return normalized or "anonymous-session"
