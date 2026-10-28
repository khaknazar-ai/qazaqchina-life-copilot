"""Bounded Alibaba requests shared by embedding and reranking adapters."""

import json
import re
import sqlite3
import time
from urllib.parse import urlsplit

import httpx
from pydantic import SecretStr

from backend.app.cloud_ai.budget import CloudLimitError, CloudRequestBudget

MAX_RESPONSE_BYTES = 4 * 1024 * 1024
RERANK_PATH = "/api/v1/services/rerank/text-rerank/text-rerank"
_WORKSPACE_HOST = re.compile(r"[a-z0-9][a-z0-9-]{0,63}\.ap-southeast-1\.maas\.aliyuncs\.com")


class RetrievalProviderError(ValueError):
    def __init__(self, code: str, *, attempts: int = 0) -> None:
        self.code = code
        self.attempts = attempts
        super().__init__(code)


def singapore_base_url(base_url: str | None) -> str:
    value = (base_url or "").rstrip("/")
    if not value.isascii() or any(character.isspace() for character in value):
        raise RetrievalProviderError("retrieval_endpoint_invalid")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise RetrievalProviderError("retrieval_endpoint_invalid") from exc
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or port
        or parsed.query
        or parsed.fragment
        or parsed.path != "/compatible-mode/v1"
        or not (
            parsed.hostname == "dashscope-intl.aliyuncs.com"
            or _WORKSPACE_HOST.fullmatch(parsed.hostname or "")
        )
    ):
        raise RetrievalProviderError("retrieval_endpoint_invalid")
    return value


class RetrievalHTTPClient:
    def __init__(
        self,
        *,
        base_url: str | None,
        api_key: SecretStr | None,
        budget: CloudRequestBudget,
        timeout_seconds: float = 30,
        max_attempts: int = 2,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = singapore_base_url(base_url)
        key = api_key.get_secret_value() if api_key else ""
        if not key or len(key) > 512 or not key.isascii() or any(c.isspace() for c in key):
            raise RetrievalProviderError("retrieval_api_key_invalid")
        if budget is None or max_attempts not in {1, 2} or not 1 <= timeout_seconds <= 60:
            raise RetrievalProviderError("retrieval_configuration_invalid")
        self._api_key = key
        self.budget = budget
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts
        self.transport = transport
        self.last_attempts = 0
        self.total_attempts = 0

    def post(self, path: str, payload: dict, *, kind: str) -> dict:
        if (path, kind) == ("/embeddings", "embedding"):
            url = self.base_url + path
        elif (path, kind) == (RERANK_PATH, "rerank"):
            url = urlsplit(self.base_url)._replace(path=RERANK_PATH).geturl()
        else:
            raise RetrievalProviderError("retrieval_path_invalid")
        self.last_attempts = 0
        for attempt in range(self.max_attempts):
            try:
                self.budget.reserve(kind)
            except CloudLimitError as exc:
                raise RetrievalProviderError(
                    "cloud_request_limit",
                    attempts=self.last_attempts,
                ) from exc
            except (OSError, sqlite3.Error) as exc:
                raise RetrievalProviderError(
                    "cloud_usage_store_unavailable",
                    attempts=self.last_attempts,
                ) from exc
            self.last_attempts += 1
            self.total_attempts += 1
            retry = False
            try:
                with (
                    httpx.Client(
                        timeout=self.timeout_seconds,
                        follow_redirects=False,
                        trust_env=False,
                        transport=self.transport,
                    ) as client,
                    client.stream(
                        "POST",
                        url,
                        json=payload,
                        headers={"Authorization": "Bearer " + self._api_key},
                    ) as response,
                ):
                    if response.status_code != 200:
                        retry = response.status_code in {429, 502, 503, 504}
                        code = {
                            401: "retrieval_auth_failed",
                            403: "retrieval_access_denied",
                            429: "retrieval_rate_limited",
                        }.get(response.status_code, "retrieval_http_error")
                        if not retry or attempt + 1 == self.max_attempts:
                            raise RetrievalProviderError(code, attempts=self.last_attempts)
                    else:
                        body = bytearray()
                        for part in response.iter_bytes():
                            body.extend(part)
                            if len(body) > MAX_RESPONSE_BYTES:
                                raise RetrievalProviderError(
                                    "retrieval_response_too_large",
                                    attempts=self.last_attempts,
                                )
                        try:
                            result = json.loads(body)
                        except (ValueError, UnicodeDecodeError) as exc:
                            raise RetrievalProviderError(
                                "retrieval_response_invalid",
                                attempts=self.last_attempts,
                            ) from exc
                        if (
                            not isinstance(result, dict)
                            or result.get("error")
                            or result.get("code")
                        ):
                            raise RetrievalProviderError(
                                "retrieval_response_invalid",
                                attempts=self.last_attempts,
                            )
                        return result
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt + 1 == self.max_attempts:
                    raise RetrievalProviderError(
                        "retrieval_transport_failed",
                        attempts=self.last_attempts,
                    ) from exc
                retry = True
            except httpx.HTTPError as exc:
                # A malformed compressed response is not a retryable transport
                # failure. Keep provider text out of API errors and CLI reports.
                raise RetrievalProviderError(
                    "retrieval_response_invalid", attempts=self.last_attempts
                ) from exc
            if retry:
                time.sleep(0.1)
        raise RetrievalProviderError("retrieval_http_error", attempts=self.last_attempts)
