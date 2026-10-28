"""Manual GET transport pinned to validated public DNS addresses; never uses proxies."""

import http.client
import ipaddress
import socket
import ssl
import time
from typing import Any
from urllib.parse import urljoin, urlsplit

from backend.app.url_fetcher.safety import validate_url_for_fetch

_REDIRECT_CODES = {301, 302, 303, 307, 308}


class PublicResponse:
    def __init__(self, response: Any, connection: Any, url: str) -> None:
        self.response = response
        self.connection = connection
        self.url = url
        self.headers = response.headers
        self.status = response.status

    def read(self, size: int = -1) -> bytes:
        return self.response.read(size)

    def geturl(self) -> str:
        return self.url

    def getcode(self) -> int:
        return self.status

    def close(self) -> None:
        try:
            self.response.close()
        finally:
            self.connection.close()


def open_public_url(
    url: str,
    timeout_seconds: float,
    max_redirects: int,
    *,
    accept_language: str | None = None,
):
    if accept_language is not None and accept_language not in {"en", "ru", "kk", "zh"}:
        raise ValueError("accept_language_not_allowed")
    redirects: list[str] = []
    current_url = url
    while True:
        check = validate_url_for_fetch(current_url)
        if not check.allowed:
            raise ValueError(f"url_not_allowed:{check.reason}")
        current_url = check.normalized_url or current_url
        parsed = urlsplit(current_url)
        host = (parsed.hostname or "").encode("idna").decode("ascii")
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        if not addresses:
            raise ValueError("dns_resolution_empty")
        # Reject mixed public/private answers too; do not select a convenient public one.
        for family, _, _, _, address in addresses:
            if family not in {socket.AF_INET, socket.AF_INET6}:
                raise ValueError("dns_address_family_not_allowed")
            ip = ipaddress.ip_address(address[0])
            if not ip.is_global or ip.is_multicast:
                raise ValueError("dns_address_not_public")
        response = _request_with_fallback(
            current_url,
            host,
            port,
            addresses,
            timeout_seconds,
            accept_language=accept_language,
        )
        location = response.headers.get("Location")
        if response.status not in _REDIRECT_CODES or not location:
            return response, redirects
        response.close()
        if len(redirects) >= max_redirects:
            raise ValueError("redirect_limit_exceeded")
        current_url = urljoin(current_url, location)
        redirects.append(current_url)


def _request_with_fallback(
    url: str,
    host: str,
    port: int,
    addresses: list,
    timeout: float,
    *,
    accept_language: str | None = None,
):
    if timeout <= 0:
        raise ValueError("timeout_must_be_positive")
    deadline = time.monotonic() + timeout
    unique = []
    seen = set()
    # IPv4 works on hosts that publish IPv6 DNS but have no usable IPv6 connection.
    for address in sorted(addresses, key=lambda item: item[0] != socket.AF_INET):
        identity = (address[0], address[4])
        if identity not in seen:
            seen.add(identity)
            unique.append(address)
    last_error = None
    for address in unique[:3]:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("public_connection_timeout")
        try:
            if accept_language is not None:
                return _request_at_address(
                    url,
                    host,
                    port,
                    address,
                    remaining,
                    accept_language=accept_language,
                )
            return _request_at_address(url, host, port, address, remaining)
        except ssl.SSLError:
            # A certificate/TLS failure is not a reason to try to bypass that failure.
            raise
        except OSError as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    raise ValueError("dns_resolution_empty")


def _request_at_address(
    url: str,
    host: str,
    port: int,
    address: tuple,
    timeout: float,
    *,
    accept_language: str | None = None,
):
    family, socket_type, protocol, _, endpoint = address
    connection = http.client.HTTPConnection(host, port=port, timeout=timeout)
    sock = socket.socket(family, socket_type, protocol)
    try:
        sock.settimeout(timeout)
        # Connect the exact validated numeric endpoint, with no second hostname lookup.
        sock.connect(endpoint)
        if urlsplit(url).scheme == "https":
            sock = ssl.create_default_context().wrap_socket(sock, server_hostname=host)
        connection.sock = sock
        parsed = urlsplit(url)
        target = parsed.path or "/"
        if parsed.query:
            target += "?" + parsed.query
        headers = {
            "User-Agent": "QminiGuide-Manual-Source-Verification/1.0",
            "Connection": "close",
        }
        if accept_language is not None:
            headers["Accept-Language"] = accept_language
        connection.request("GET", target, headers=headers)
        return PublicResponse(connection.getresponse(), connection, url)
    except BaseException:
        sock.close()
        connection.close()
        raise
