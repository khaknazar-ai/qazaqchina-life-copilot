"""Bound ingress before JSON parsing, authenticate pilot clients and limit concurrency."""

import asyncio
import hashlib
import ipaddress
import time
from collections import deque
from urllib.parse import urlsplit

from fastapi import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from backend.app.api_utils.identity_boundary import IdentityResolver
from backend.app.api_utils.local_device_signin import PUBLIC_SIGNIN_PATHS
from backend.app.api_utils.pilot_access import PilotAccessService
from backend.app.config import get_settings

# Only the login shell is public; its data endpoints enforce admin auth/RBAC.
PUBLIC_GET_PATHS = {
    "/admin/source-corpus", "/admin/source-corpus/corpus.js", "/admin/source-corpus/corpus.css",
    "/admin/source-conflicts",
    "/admin/source-conflicts/conflicts.js",
    "/admin/source-conflicts/conflicts.css",
    "/admin/evaluation", "/admin/evaluation/evaluation.js",
    "/health", "/api/capabilities", "/api/photo-intake/mode",
    "/admin/source-console",
    "/admin/source-console/admin_source_console.js",
    "/admin/source-console/admin_source_console.css",
}


class RequestGuard:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.inflight = 0
        self.windows: dict[tuple[str, str], deque] = {}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        state = scope["app"].state
        settings = getattr(state, "runtime_settings", None) or get_settings()
        access = getattr(state, "pilot_access_service", None) or PilotAccessService(settings)
        path, method = scope["path"], scope["method"]
        host = (scope.get("client") or ("", 0))[0]
        local_signin = method == "POST" and path in PUBLIC_SIGNIN_PATHS
        if local_signin and not _local_signin_origin(
            scope, settings.LOCAL_DEVICE_SIGNIN_DEVTOOLS_REFERER,
        ):
            await self._reject(scope, receive, send, 403, "local_signin_loopback_required")
            return
        if not access.required and not _is_loopback(host):
            await self._reject(scope, receive, send, 403, "local_demo_only")
            return
        if not access.required and not _local_demo_host(scope):
            await self._reject(scope, receive, send, 403, "local_demo_host_required")
            return
        if self.inflight >= settings.API_MAX_CONCURRENT_REQUESTS:
            await self._reject(scope, receive, send, 429, "request_concurrency_limit")
            return
        self.inflight += 1
        try:
            if access.required:
                ip_key = hashlib.sha256(host.encode()).hexdigest()
                if not self._reserve("ip", ip_key, settings.API_IP_REQUESTS_PER_MINUTE):
                    await self._reject(scope, receive, send, 429, "ip_request_limit")
                    return
                admin_route = _admin_route(path, method)
                if admin_route and not settings.ADMIN_AUTH_ENABLED:
                    await self._reject(scope, receive, send, 403, "admin_access_not_configured")
                    return
                public = method == "GET" and path in PUBLIC_GET_PATHS
                public = public or (
                    local_signin and getattr(state, "local_device_signin", None) is not None
                )
                if not public and not admin_route:
                    headers = [v for k, v in scope["headers"] if k.lower() == b"authorization"]
                    principal = (
                        access.authenticate(headers[0].decode("latin1"))
                        if len(headers) == 1 else None
                    )
                    if principal is None:
                        await self._reject(scope, receive, send, 401, "pilot_access_required")
                        return
                    resolver = getattr(state, "identity_resolver", None) or IdentityResolver(access)
                    if not isinstance(resolver, IdentityResolver):
                        await self._reject(scope, receive, send, 401, "identity_not_trusted")
                        return
                    try:
                        identity = resolver.resolve(principal)
                    except HTTPException as error:
                        await self._reject(scope, receive, send, error.status_code, error.detail)
                        return
                    if not self._reserve(
                        "user", identity.owner, settings.API_USER_REQUESTS_PER_MINUTE,
                    ):
                        await self._reject(scope, receive, send, 429, "user_request_limit")
                        return
                    scope.setdefault("state", {})["pilot_principal"] = principal
            limit = (
                settings.API_MAX_IMAGE_BODY_BYTES if path == "/api/photo-intake/preview"
                else settings.API_MAX_BODY_BYTES
            )
            lengths = [v for k, v in scope["headers"] if k.lower() == b"content-length"]
            try:
                if len(lengths) > 1 or lengths and (int(lengths[0]) < 0 or int(lengths[0]) > limit):
                    await self._reject(scope, receive, send, 413, "request_body_too_large")
                    return
            except ValueError:
                await self._reject(scope, receive, send, 400, "invalid_content_length")
                return
            body = bytearray()
            try:
                async with asyncio.timeout(settings.API_BODY_TIMEOUT_SECONDS):
                    while True:
                        message = await receive()
                        if message["type"] == "http.disconnect":
                            return
                        chunk = message.get("body", b"")
                        if len(body) + len(chunk) > limit:
                            await self._reject(scope, receive, send, 413, "request_body_too_large")
                            return
                        body.extend(chunk)
                        if not message.get("more_body", False):
                            break
            except TimeoutError:
                await self._reject(scope, receive, send, 408, "request_body_timeout")
                return
            delivered = False

            async def bounded_receive():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await receive()

            await self.app(scope, bounded_receive, send)
        finally:
            self.inflight -= 1

    def _reserve(self, kind: str, key: str, limit: int) -> bool:
        now = time.monotonic()
        # Bound memory even under many unauthenticated connections. Never evict a
        # live window, which would allow an attacker to reset a rate limit.
        self.windows = {k: v for k, v in self.windows.items() if v and v[-1] > now - 60}
        bucket = (kind, key)
        if bucket not in self.windows and len(self.windows) >= 4096:
            return False
        window = self.windows.setdefault(bucket, deque())
        while window and window[0] <= now - 60:
            window.popleft()
        if len(window) >= limit:
            return False
        window.append(now)
        return True

    @staticmethod
    async def _reject(scope, receive, send, status: int, code: str) -> None:
        await JSONResponse({"detail": code}, status_code=status)(scope, receive, send)


def _is_loopback(host: str) -> bool:
    if host == "testclient":  # Starlette's in-process transport, never an HTTP header.
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _local_signin_origin(scope: Scope, devtools_referer: str = "") -> bool:
    """Accept the project's native Mini Program request on the local demo host.

    WeChat ``wx.request`` does not consistently send browser ``Sec-Fetch-*``
    metadata. The loopback peer, local Host, exact DevTools Referer, custom
    marker, and JSON content type keep this endpoint scoped to this demo. These
    request markers are not user identity.
    """
    headers = scope.get("headers", [])
    content_types = [v for k, v in headers if k.lower() == b"content-type"]
    referers = [v for k, v in headers if k.lower() == b"referer"]
    local_headers = [v for k, v in headers if k.lower() == b"x-q-local-access"]
    devtools = bool(devtools_referer) and referers == [devtools_referer.encode("ascii")]
    return (
        _is_loopback((scope.get("client") or ("", 0))[0]) and _local_demo_host(scope)
        and not any(k.lower() == b"origin" for k, _ in headers)
        and devtools and local_headers == [b"devtools"]
        and len(content_types) == 1
        and content_types[0].split(b";", 1)[0].strip().lower() == b"application/json"
    )


def _admin_route(path: str, method: str) -> bool:
    return (
        path.startswith("/api/admin/") or path == "/api/admin"
        or path.startswith("/api/traces")
        or path == "/api/cases" and method == "GET"
    )


def _local_demo_host(scope: Scope) -> bool:
    """A loopback peer alone cannot establish a browser's trusted origin."""
    headers = [value for key, value in scope["headers"] if key.lower() == b"host"]
    if len(headers) != 1:
        return False
    try:
        authority = headers[0].decode("ascii")
        if not authority or any(ord(char) <= 32 or ord(char) >= 127 for char in authority):
            return False
        parsed = urlsplit("//" + authority)
        if (
            parsed.netloc != authority or parsed.path or parsed.query or parsed.fragment
            or parsed.username is not None or parsed.password is not None
            or authority.endswith(":") or parsed.port is not None and parsed.port < 1
        ):
            return False
        hostname = parsed.hostname
    except (ValueError, UnicodeDecodeError):
        return False
    if hostname == "testserver" and (scope.get("client") or ("", 0))[0] == "testclient":
        return True  # Starlette's in-process transport, never a real socket peer.
    if hostname == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname or "").is_loopback
    except ValueError:
        return False
