import http.client
from hashlib import sha256
from typing import Any
from urllib import request

from backend.app.source_candidates.models import SourceCandidate, utc_now
from backend.app.tools.policies import (
    guess_source_type_from_url,
    infer_domain_from_url,
    looks_like_official_domain,
)
from backend.app.url_fetcher.extractor import (
    content_hash,
    decode_response_bytes,
    extract_text_preview_from_html,
    extract_title_from_html,
)
from backend.app.url_fetcher.models import (
    URLFetchRequest,
    URLFetchResult,
    URLSafetyCheck,
    URLToCandidateResult,
)
from backend.app.url_fetcher.safety import (
    validate_redirect_chain,
    validate_url_for_fetch,
)
from backend.app.url_fetcher.transport import open_public_url

_SAFE_USER_AGENT = "QminiGuide-Manual-Source-Verification/1.0"
_TEXT_CONTENT_TYPES = ("text/html", "text/plain", "application/xhtml+xml")


class ControlledURLFetcher:
    def validate(self, request_data: URLFetchRequest) -> URLSafetyCheck:
        return validate_url_for_fetch(request_data.url)

    def fetch(
        self,
        request_data: URLFetchRequest,
        opener: Any = None,
    ) -> URLFetchResult:
        safety = self.validate(request_data)
        if not safety.allowed:
            return URLFetchResult(
                url=request_data.url,
                final_url=safety.normalized_url,
                warnings=safety.warnings,
                error=safety.reason or "url_not_allowed",
            )

        target_url = safety.normalized_url or request_data.url
        warnings = list(safety.warnings)
        if not request_data.allow_network:
            return URLFetchResult(
                url=request_data.url,
                final_url=target_url,
                fetched=False,
                used_network=False,
                warnings=[*warnings, "network_disabled"],
            )

        response = None
        try:
            response, redirect_urls = _open_url(
                target_url,
                timeout_seconds=request_data.timeout_seconds,
                max_redirects=request_data.max_redirects,
                opener=opener,
            )
            final_url = _response_final_url(response) or target_url
            redirect_check = validate_redirect_chain([target_url, *redirect_urls, final_url])
            if not redirect_check.allowed:
                return URLFetchResult(
                    url=request_data.url,
                    final_url=final_url,
                    fetched=False,
                    used_network=True,
                    warnings=[*warnings, *redirect_check.warnings],
                    error=redirect_check.reason or "redirect_not_allowed",
                )
            status_code = _status_code(response)
            if type(status_code) is not int or not 200 <= status_code < 300:
                return URLFetchResult(
                    url=request_data.url,
                    final_url=final_url,
                    fetched=False,
                    used_network=True,
                    status_code=status_code,
                    warnings=warnings,
                    error=(
                        f"http_status_{status_code}"
                        if type(status_code) is int
                        else "http_status_unavailable"
                    ),
                )
            content_type = _content_type(response)
            data = response.read(max(0, request_data.max_bytes) + 1)
        except (OSError, ValueError, http.client.HTTPException) as exc:
            return URLFetchResult(
                url=request_data.url,
                final_url=target_url,
                fetched=False,
                used_network=True,
                warnings=warnings,
                error=_safe_error(exc),
            )
        finally:
            if response is not None and hasattr(response, "close"):
                response.close()

        if len(data) > request_data.max_bytes:
            warnings.append("response_truncated_to_max_bytes")
            data = data[: request_data.max_bytes]

        status_code = _status_code(response)
        final_url = _response_final_url(response) or target_url
        if not _is_supported_content_type(content_type):
            warnings.append("unsupported_content_type")
            return URLFetchResult(
                url=request_data.url,
                final_url=final_url,
                fetched=True,
                used_network=True,
                status_code=status_code,
                content_type=content_type,
                bytes_read=len(data),
                warnings=list(dict.fromkeys(warnings)),
            )

        decoded = decode_response_bytes(data, content_type)
        title = extract_title_from_html(decoded) if _is_html(content_type) else None
        preview = (
            extract_text_preview_from_html(decoded)
            if _is_html(content_type)
            else " ".join(decoded.split())[:1200]
        )
        return URLFetchResult(
            url=request_data.url,
            final_url=final_url,
            fetched=True,
            used_network=True,
            status_code=status_code,
            content_type=content_type,
            title=title,
            text_preview=preview,
            content_hash=content_hash(decoded),
            bytes_read=len(data),
            warnings=list(dict.fromkeys(warnings)),
        )

    def fetch_to_source_candidate(
        self,
        request_data: URLFetchRequest,
        opener: Any = None,
    ) -> URLToCandidateResult:
        fetch_result = self.fetch(request_data, opener=opener)
        warnings = list(fetch_result.warnings)
        if fetch_result.error and "network_disabled" not in warnings:
            return URLToCandidateResult(
                fetch_result=fetch_result,
                candidate=None,
                warnings=list(dict.fromkeys(warnings)),
            )
        candidate = _candidate_from_fetch_result(request_data, fetch_result)
        return URLToCandidateResult(
            fetch_result=fetch_result,
            candidate=candidate,
            warnings=list(dict.fromkeys([*warnings, *candidate.warnings])),
        )


def _candidate_from_fetch_result(
    request_data: URLFetchRequest,
    fetch_result: URLFetchResult,
) -> SourceCandidate:
    url = fetch_result.final_url or request_data.url
    domain = infer_domain_from_url(url)
    title = fetch_result.title or f"Manual URL source candidate: {domain or url}"
    snippet = fetch_result.text_preview or "URL not fetched; manual review required."
    source_type_guess = guess_source_type_from_url(url)
    warnings = [
        *fetch_result.warnings,
        "Fetched content is not trusted evidence.",
        "Candidate is not added to trusted registry automatically.",
        "not_trusted_until_review",
    ]
    if not fetch_result.fetched:
        warnings.append("URL not fetched; manual review required.")
    candidate_key = f"{url}|{title}|controlled_url_fetcher".encode()
    return SourceCandidate(
        candidate_id=f"SRC-URL-{sha256(candidate_key).hexdigest()[:12].upper()}",
        title=title,
        url=url,
        snippet=snippet[:500],
        domain=domain,
        source_type_guess=source_type_guess,
        trust_guess="unreviewed_url_candidate",
        language=request_data.language,
        city=request_data.city,
        scenario=request_data.scenario,
        risk_level=request_data.risk_level,
        official_domain_hint=looks_like_official_domain(url),
        requires_review=True,
        status="pending",
        warnings=list(dict.fromkeys(warnings)),
        discovered_by="controlled_url_fetcher",
        created_at=utc_now(),
        allow_retrieval=False,
        freshness_note=(
            f"Fetched content hash: {fetch_result.content_hash}"
            if fetch_result.content_hash
            else None
        ),
    )


def _open_url(
    url: str,
    timeout_seconds: float,
    max_redirects: int,
    opener: Any = None,
):
    if opener is not None:
        response = opener.open(_request(url), timeout=timeout_seconds)
        return response, []
    return open_public_url(url, timeout_seconds, max_redirects)


def _request(url: str) -> request.Request:
    return request.Request(url, headers={"User-Agent": _SAFE_USER_AGENT})


def _status_code(response: Any) -> int | None:
    if hasattr(response, "getcode"):
        return response.getcode()
    return getattr(response, "status", None)


def _response_final_url(response: Any) -> str | None:
    if hasattr(response, "geturl"):
        return response.geturl()
    return getattr(response, "url", None)


def _content_type(response: Any) -> str | None:
    headers = getattr(response, "headers", None)
    if headers is not None and hasattr(headers, "get"):
        value = headers.get("Content-Type") or headers.get("content-type")
        if value:
            return str(value)
    if hasattr(response, "getheader"):
        value = response.getheader("Content-Type")
        if value:
            return str(value)
    return None


def _is_supported_content_type(content_type: str | None) -> bool:
    if content_type is None:
        return True
    normalized = content_type.split(";", 1)[0].strip().casefold()
    return normalized.startswith("text/") or normalized in _TEXT_CONTENT_TYPES


def _is_html(content_type: str | None) -> bool:
    if content_type is None:
        return True
    normalized = content_type.split(";", 1)[0].strip().casefold()
    return normalized in {"text/html", "application/xhtml+xml"}


def _safe_error(exc: BaseException) -> str:
    value = str(exc) or exc.__class__.__name__
    if len(value) > 160:
        value = value[:160]
    return value
