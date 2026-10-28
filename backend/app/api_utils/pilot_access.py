"""Individual, revocable pilot credentials; never a substitute for WeChat identity."""

import hashlib
import hmac
import json
import re
import secrets
import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Literal, TypeVar

from fastapi import HTTPException, Request
from pydantic import BaseModel

from backend.app.config import Settings

Model = TypeVar("Model", bound=BaseModel)


@dataclass(frozen=True)
class PilotPrincipal:
    actor_id: str
    namespace_key: bytes = field(repr=False)
    account_type: Literal["citizen", "consul"] = "citizen"
    local_preview: bool = False

    def session_id(self, client_id: str) -> str:
        digest = hmac.new(self.namespace_key, client_id.encode(), hashlib.sha256).hexdigest()
        return "pilot-" + digest


class PilotAccessService:
    def __init__(self, settings: Settings) -> None:
        raw = settings.PILOT_ACCESS_TOKENS.get_secret_value()
        self.required = bool(raw) or any((
            settings.QWEN_CHAT_ENABLED, settings.QWEN_OCR_ENABLED,
            settings.CLOUD_RETRIEVAL_ENABLED, settings.SEMANTIC_CONFLICT_REVIEW_ENABLED,
        ))
        self._credentials: list[tuple[bytes, PilotPrincipal]] = []
        self._local_sessions: dict[bytes, tuple[PilotPrincipal, float]] = {}
        self._session_lock = Lock()
        self._session_clock = time.monotonic
        if not self.required:
            return
        try:
            pairs = json.loads(raw, object_pairs_hook=_unique_pairs)
            if not isinstance(pairs, dict) or not 1 <= len(pairs) <= 100:
                raise ValueError
            account_types = json.loads(
                settings.PILOT_ACCOUNT_TYPES, object_pairs_hook=_unique_pairs,
            )
            if (not isinstance(account_types, dict) or set(account_types) - set(pairs)
                    or any(role not in {"citizen", "consul"} for role in account_types.values())):
                raise ValueError
            seen = set()
            reserved = {
                settings.DASHSCOPE_API_KEY.get_secret_value(),
                settings.ADMIN_AUTH_TOKEN.get_secret_value(),
                settings.ADMIN_REVIEW_AUTH_TOKEN.get_secret_value(),
                settings.LLM_API_KEY,
            }
            for actor, token in pairs.items():
                if not isinstance(actor, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", actor):
                    raise ValueError
                if (
                    not isinstance(token, str) or not 32 <= len(token) <= 256
                    or not all(33 <= ord(c) <= 126 for c in token)
                    or token in seen or token in reserved
                ):
                    raise ValueError
                seen.add(token)
                digest = hashlib.sha256(token.encode()).digest()
                self._credentials.append((digest, PilotPrincipal(
                    actor, digest, account_types.get(actor, "citizen"),
                )))
        except (ValueError, TypeError):
            raise ValueError(
                "Cloud/pilot mode requires PILOT_ACCESS_TOKENS: a JSON mapping of distinct "
                "participant IDs to distinct printable ASCII access tokens of 32-256 characters. "
                "Do not reuse provider or administrator credentials. "
                "PILOT_ACCOUNT_TYPES must map known participant IDs to citizen or consul."
            ) from None

    def authenticate(self, header: str) -> PilotPrincipal | None:
        scheme, _, token = header.partition(" ")
        if scheme.casefold() != "bearer" or not token.isascii() or not 32 <= len(token) <= 256:
            return None
        digest = hashlib.sha256(token.encode()).digest()
        for expected, principal in self._credentials:
            if hmac.compare_digest(expected, digest):
                return principal
        with self._session_lock:
            self._expire_sessions()
            session = self._local_sessions.get(digest)
            if session is not None:
                return session[0]
        return None

    def configured_accounts(self) -> dict[str, str]:
        return {principal.actor_id: principal.account_type for _, principal in self._credentials}

    def is_issued_principal(self, principal: PilotPrincipal) -> bool:
        if any(principal is configured for _, configured in self._credentials):
            return True
        with self._session_lock:
            self._expire_sessions()
            return any(principal is value[0] for value in self._local_sessions.values())

    @property
    def supports_local_owner(self) -> bool:
        return (len(self._credentials) == 1
                and self._credentials[0][1].actor_id == "local-owner"
                and self._credentials[0][1].account_type == "citizen")

    def _expire_sessions(self) -> None:
        now = self._session_clock()
        self._local_sessions = {
            digest: value for digest, value in self._local_sessions.items() if value[1] > now
        }

    def issue_local_session(self, account_type: Literal["citizen", "consul"] = "citizen") -> str:
        """Issue an ephemeral credential for the fixed local development owner."""
        if not self.supports_local_owner:
            raise ValueError("A single local-owner credential is required")
        if account_type not in {"citizen", "consul"}:
            raise ValueError("Unknown local account type")
        owner = self._credentials[0][1]
        if account_type == "consul":
            # Separate stable namespace; never changes the existing citizen owner.
            owner = PilotPrincipal("local-consul", hmac.new(
                owner.namespace_key, b"local-consul", hashlib.sha256,
            ).digest(), "consul", True)
        else:
            owner = PilotPrincipal(owner.actor_id, owner.namespace_key, "citizen", True)
        with self._session_lock:
            self._expire_sessions()
            if len(self._local_sessions) >= 32:
                raise HTTPException(429, "local_session_limit")
            token = secrets.token_urlsafe(32)
            self._local_sessions[hashlib.sha256(token.encode()).digest()] = (
                owner, self._session_clock() + 7200,
            )
        return token

    def revoke_local_session(self, header: str) -> None:
        scheme, _, token = header.partition(" ")
        if scheme.casefold() == "bearer" and token.isascii():
            with self._session_lock:
                self._local_sessions.pop(hashlib.sha256(token.encode()).digest(), None)


def _unique_pairs(pairs: list[tuple[str, str]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def bind_citizen_request(http_request: Request, model: Model) -> Model:
    """Client IDs only select a conversation inside the authenticated namespace."""
    principal = getattr(http_request.state, "pilot_principal", None)
    if principal is None:
        return model
    from backend.app.api_utils.identity_boundary import request_identity

    identity = request_identity(http_request)
    updates = {}
    if "user_id" in type(model).model_fields:
        claimed_user = getattr(model, "user_id", None)
        if claimed_user and claimed_user != identity.actor_id:
            raise HTTPException(403, "user_identity_mismatch")
        updates["user_id"] = identity.actor_id
    if "session_id" in type(model).model_fields:
        session = getattr(model, "session_id", None)
        if session is not None:
            if not 1 <= len(session) <= 128:
                raise HTTPException(422, "invalid_session_id")
            updates["session_id"] = principal.session_id(session)
    return model.model_copy(update=updates)
