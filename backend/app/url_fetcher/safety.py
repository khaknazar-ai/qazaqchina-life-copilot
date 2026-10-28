import ipaddress
from urllib.parse import ParseResult, urlparse, urlunparse

from backend.app.url_fetcher.models import URLSafetyCheck

_ALLOWED_SCHEMES = {"http", "https"}
_BLOCKED_SCHEMES = {"file", "ftp", "data", "javascript", "mailto"}
_INTERNAL_HOST_SUFFIXES = (".local", ".internal", ".localhost")
_INTERNAL_HOSTNAMES = {"localhost", "local", "internal"}
_CLOUD_METADATA_HOSTS = {"169.254.169.254"}


def normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    scheme = parsed.scheme.casefold()
    hostname = (parsed.hostname or "").casefold()
    netloc = f"[{hostname}]" if ":" in hostname else hostname
    if parsed.port is not None:
        netloc = f"{netloc}:{parsed.port}"
    path = parsed.path or "/"
    return urlunparse(
        ParseResult(
            scheme=scheme,
            netloc=netloc,
            path=path,
            params="",
            query=parsed.query,
            fragment="",
        )
    )


def is_private_or_loopback_host(hostname: str) -> bool:
    normalized = hostname.strip("[]").casefold()
    if normalized in _CLOUD_METADATA_HOSTS:
        return True
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return _is_internal_hostname(normalized)
    return not address.is_global or any(
        [
            address.is_private,
            address.is_loopback,
            address.is_link_local,
            address.is_reserved,
            address.is_multicast,
            address.is_unspecified,
        ]
    )


def validate_url_for_fetch(url: str) -> URLSafetyCheck:
    stripped = url.strip()
    try:
        parsed = urlparse(stripped)
        hostname = parsed.hostname
    except ValueError:
        return _blocked(url, "malformed_hostname")
    scheme = parsed.scheme.casefold()
    warnings: list[str] = []

    if not stripped:
        return _blocked(url, "empty_url")
    if scheme in _BLOCKED_SCHEMES:
        return _blocked(url, f"scheme_not_allowed:{scheme}")
    if scheme not in _ALLOWED_SCHEMES:
        return _blocked(url, "scheme_not_allowed")
    if not hostname:
        return _blocked(url, "missing_hostname")
    if parsed.username or parsed.password:
        return _blocked(url, "url_credentials_not_allowed")
    try:
        parsed.port
    except ValueError:
        return _blocked(url, "malformed_port")
    if is_private_or_loopback_host(parsed.hostname):
        return _blocked(url, "host_not_allowed")
    if parsed.hostname.casefold().startswith("."):
        return _blocked(url, "malformed_hostname")

    normalized_url = normalize_url(stripped)
    if normalized_url != stripped:
        warnings.append("url_normalized")
    return URLSafetyCheck(
        url=url,
        allowed=True,
        normalized_url=normalized_url,
        warnings=warnings,
    )


def validate_redirect_chain(urls: list[str]) -> URLSafetyCheck:
    if not urls:
        return _blocked("", "empty_redirect_chain")
    warnings: list[str] = []
    final_check: URLSafetyCheck | None = None
    for index, url in enumerate(urls):
        check = validate_url_for_fetch(url)
        if not check.allowed:
            return URLSafetyCheck(
                url=url,
                allowed=False,
                normalized_url=check.normalized_url,
                reason=f"redirect_{index}_{check.reason or 'not_allowed'}",
                warnings=[*warnings, *check.warnings],
            )
        warnings.extend(check.warnings)
        final_check = check
    return URLSafetyCheck(
        url=urls[-1],
        allowed=True,
        normalized_url=final_check.normalized_url if final_check is not None else urls[-1],
        warnings=list(dict.fromkeys(warnings)),
    )


def _blocked(url: str, reason: str) -> URLSafetyCheck:
    return URLSafetyCheck(url=url, allowed=False, reason=reason)


def _is_internal_hostname(hostname: str) -> bool:
    normalized = hostname.casefold().strip(".")
    if normalized in _INTERNAL_HOSTNAMES:
        return True
    if any(normalized.endswith(suffix) for suffix in _INTERNAL_HOST_SUFFIXES):
        return True
    return "." not in normalized
