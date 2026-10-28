"""Server-authenticated identities and queue grants; no login or enrollment API.

ExternalPrincipal is a handoff from a future trusted authenticator, never a JSON
request schema. This module does not verify platform credentials. No external
issuer or staff grant is installed by default. Grants are process-local; durable
institutional approval/revocation remains a separate integration requirement.
"""

import hashlib
import json
from dataclasses import dataclass, field
from threading import Lock
from typing import Literal

from fastapi import HTTPException, Request

from backend.app.api_utils.pilot_access import PilotAccessService, PilotPrincipal

Realm = Literal["preview", "pilot", "external"]


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _pilot_owner(actor: str) -> str:
    return "pilot:" + _digest(actor)


PREVIEW_OWNERS = frozenset(_pilot_owner(actor) for actor in ("local-owner", "local-consul"))


def is_persistent_owner(owner: str) -> bool:
    # Existing service stores accepted all pilot-prefixed record keys. Preserve
    # that storage contract; only the resolver constructs authenticated owners.
    if owner.startswith("pilot:"):
        return True
    parts = owner.split(":")
    return (
        len(parts) == 3 and parts[0] == "external"
        and all(len(part) == 64 and all(c in "0123456789abcdef" for c in part)
                for part in parts[1:])
    )


@dataclass(frozen=True)
class IdentityKey:
    realm: Realm
    issuer: str
    subject: str = field(repr=False)


@dataclass(frozen=True)
class ExternalPrincipal:
    """Verified server handoff only. Constructing this object is not authentication."""

    issuer: str
    subject: str = field(repr=False)

    @property
    def actor_id(self) -> str:
        return "external-user:" + _digest(
            json.dumps([self.issuer, self.subject], ensure_ascii=True),
        )

    @property
    def owner(self) -> str:
        return "external:" + _digest(self.issuer) + ":" + _digest(self.subject)

    def session_id(self, client_id: str) -> str:
        return "external-session-" + _digest(json.dumps(
            [self.issuer, self.subject, client_id], ensure_ascii=True,
        ))


class TrustedStaffGrants:
    """Server-owned allowlist. Revocation is checked on each resolved request."""

    def __init__(self, identities: tuple[IdentityKey, ...] = ()) -> None:
        self._active = set(identities)
        self._lock = Lock()

    def contains(self, key: IdentityKey) -> bool:
        with self._lock:
            return key in self._active

    def revoke(self, key: IdentityKey) -> None:
        with self._lock:
            self._active.discard(key)


@dataclass(frozen=True)
class ResolvedIdentity:
    key: IdentityKey
    owner: str
    actor_id: str
    account_type: Literal["citizen", "consul"]
    local_preview: bool

    def allows_queue_owner(self, owner: str) -> bool:
        if self.account_type != "consul" or not is_persistent_owner(owner):
            return False
        if self.key.realm == "preview":
            return owner in PREVIEW_OWNERS
        if self.key.realm == "pilot":
            return owner.startswith("pilot:") and owner not in PREVIEW_OWNERS
        return owner.startswith("external:" + _digest(self.key.issuer) + ":")


class IdentityResolver:
    def __init__(
        self, pilot: PilotAccessService, *, preview_enabled: bool = False,
        trusted_issuers: frozenset[str] = frozenset(),
        staff_grants: TrustedStaffGrants | None = None,
    ) -> None:
        self._pilot = pilot
        self._preview_enabled = preview_enabled and pilot.supports_local_owner
        self._trusted_issuers = frozenset(trusted_issuers)
        # Preserve only the assignments already made by trusted pilot config.
        configured = tuple(
            IdentityKey("pilot", "configured-pilot", actor)
            for actor, role in pilot.configured_accounts().items()
            if role == "consul" and _pilot_owner(actor) not in PREVIEW_OWNERS
        )
        if self._preview_enabled:
            configured += (IdentityKey("preview", "isolated-local", "local-consul"),)
        self.staff_grants = (
            staff_grants if staff_grants is not None else TrustedStaffGrants(configured)
        )

    def resolve(self, principal: PilotPrincipal | ExternalPrincipal) -> ResolvedIdentity:
        if type(principal) is PilotPrincipal:
            if not self._pilot.is_issued_principal(principal):
                raise HTTPException(401, "identity_not_trusted")
            owner = _pilot_owner(principal.actor_id)
            preview = owner in PREVIEW_OWNERS
            if principal.local_preview and (not self._preview_enabled or not preview):
                raise HTTPException(401, "identity_not_trusted")
            key = IdentityKey(
                "preview" if preview else "pilot",
                "isolated-local" if preview else "configured-pilot", principal.actor_id,
            )
            # The reserved legacy local owners never gain institutional queue access.
            eligible = principal.account_type == "consul" and (
                not preview or self._preview_enabled and principal.local_preview
            )
            local_preview = principal.local_preview
        elif type(principal) is ExternalPrincipal:
            if (
                not isinstance(principal.issuer, str)
                or principal.issuer not in self._trusted_issuers
                or not isinstance(principal.subject, str)
                or not 1 <= len(principal.subject) <= 256
                or any(ord(c) < 32 for c in principal.subject)
            ):
                raise HTTPException(401, "identity_not_trusted")
            key = IdentityKey("external", principal.issuer, principal.subject)
            owner, eligible, local_preview = principal.owner, True, False
        else:
            raise HTTPException(401, "identity_not_trusted")
        return ResolvedIdentity(
            key=key, owner=owner, actor_id=principal.actor_id,
            account_type="consul" if eligible and self.staff_grants.contains(key) else "citizen",
            local_preview=local_preview,
        )


def request_identity(request: Request) -> ResolvedIdentity | None:
    principal = getattr(request.state, "pilot_principal", None)
    if principal is None:
        return None
    resolver = getattr(request.app.state, "identity_resolver", None)
    if not isinstance(resolver, IdentityResolver):
        raise HTTPException(401, "identity_not_trusted")
    # Do not cache staff authorization on the request principal/session.
    return resolver.resolve(principal)
