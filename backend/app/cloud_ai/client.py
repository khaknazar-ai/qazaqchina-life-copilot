"""Alibaba Cloud's compatible HTTP API, bounded responses and no automatic retries."""

import json
import re
import sqlite3
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from backend.app.cloud_ai.budget import CloudLimitError, CloudRequestBudget
from backend.app.config import Settings

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MAX_RESPONSE_BYTES = 262144


class CloudAIError(Exception):
    def __init__(self, code: str, *, attempted: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.attempted = attempted


def validate_cloud_settings(settings: Settings) -> str:
    if settings.QWEN_RERANK_ENABLED and not settings.CLOUD_RETRIEVAL_ENABLED:
        raise CloudAIError("reranking_requires_cloud_retrieval")
    if settings.SEMANTIC_CONFLICT_REVIEW_ENABLED and not settings.QWEN_CHAT_ENABLED:
        raise CloudAIError("semantic_conflict_review_requires_cloud_chat")
    if not any((settings.QWEN_CHAT_ENABLED, settings.QWEN_OCR_ENABLED,
                settings.CLOUD_RETRIEVAL_ENABLED, settings.SEMANTIC_CONFLICT_REVIEW_ENABLED)):
        return "disabled"
    key = settings.DASHSCOPE_API_KEY.get_secret_value()
    if not key or not key.isascii() or any(character.isspace() for character in key):
        raise CloudAIError("cloud_api_key_missing_or_invalid")
    url = settings.DASHSCOPE_BASE_URL.rstrip("/")
    try:
        parsed = urlsplit(url)
        host = parsed.hostname or ""
        workspace = re.fullmatch(
            r"[a-z0-9-]+\.(cn-beijing|ap-southeast-1|cn-hongkong|"
            r"ap-northeast-1|eu-central-1|us-east-1)\.maas\.aliyuncs\.com",
            host,
        )
        legacy = host in {
            "dashscope.aliyuncs.com",
            "dashscope-intl.aliyuncs.com",
            "cn-hongkong.dashscope.aliyuncs.com",
        }
        valid = (
            parsed.scheme == "https"
            and (workspace or legacy)
            and parsed.port in {None, 443}
            and not parsed.username
            and not parsed.password
            and not parsed.query
            and not parsed.fragment
            and parsed.path == "/compatible-mode/v1"
        )
    except ValueError:
        valid = False
    if not valid:
        raise CloudAIError("cloud_endpoint_invalid")
    # This OCR model is listed only for Beijing. Reject the known mismatch
    # locally; newer models still require explicit regional availability checks.
    if (
        settings.QWEN_OCR_ENABLED
        and settings.QWEN_OCR_MODEL == "qwen3.5-ocr"
        and host != "dashscope.aliyuncs.com"
        and not host.endswith(".cn-beijing.maas.aliyuncs.com")
    ):
        raise CloudAIError("cloud_ocr_model_region_unsupported")
    for model in (settings.QWEN_CHAT_MODEL, settings.QWEN_OCR_MODEL,
                  settings.QWEN_EMBEDDING_MODEL, settings.QWEN_RERANK_MODEL):
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", model):
            raise CloudAIError("cloud_model_invalid")
    if settings.CLOUD_RETRIEVAL_ENABLED and settings.QWEN_EMBEDDING_DIMENSIONS not in {
        64, 128, 256, 512, 768, 1024, 1536, 2048,
    }:
        raise CloudAIError("cloud_embedding_dimensions_invalid")
    if settings.CLOUD_RETRIEVAL_ENABLED and settings.QWEN_EMBEDDING_MODEL != "text-embedding-v4":
        raise CloudAIError("cloud_embedding_model_unsupported")
    if settings.QWEN_RERANK_ENABLED and settings.QWEN_RERANK_MODEL != "qwen3-rerank":
        raise CloudAIError("cloud_reranking_model_unsupported")
    data_dir = Path(settings.LOCAL_DATA_DIR)
    data_dir = (
        (PROJECT_ROOT / data_dir).resolve() if not data_dir.is_absolute() else data_dir.resolve()
    )
    if not data_dir.is_relative_to(PROJECT_ROOT):
        raise CloudAIError("cloud_storage_must_be_project_local")
    return url


class QwenCloudClient:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None) -> None:
        self.settings = settings
        self.transport = transport
        self.base_url = validate_cloud_settings(settings)
        data_dir = Path(settings.LOCAL_DATA_DIR)
        if not data_dir.is_absolute():
            data_dir = PROJECT_ROOT / data_dir
        self.budget = CloudRequestBudget(
            data_dir / "cloud_usage.sqlite3",
            settings.QWEN_DAILY_REQUEST_LIMIT,
            settings.QWEN_REQUESTS_PER_MINUTE,
        )

    def complete(self, messages: list[dict[str, Any]], *, kind: str) -> tuple[str, dict]:
        enabled = (
            self.settings.QWEN_CHAT_ENABLED if kind == "chat" else self.settings.QWEN_OCR_ENABLED
        )
        if kind not in {"chat", "ocr"} or not enabled:
            raise CloudAIError("cloud_disabled")
        model = self.settings.QWEN_CHAT_MODEL if kind == "chat" else self.settings.QWEN_OCR_MODEL
        limit = (
            self.settings.QWEN_CHAT_MAX_TOKENS
            if kind == "chat"
            else self.settings.QWEN_OCR_MAX_TOKENS
        )
        payload: dict[str, Any] = {"model": model, "messages": messages, "max_tokens": limit}
        if kind == "chat":
            payload.update(enable_thinking=False, response_format={"type": "json_object"})
        try:
            self.budget.reserve(kind)
        except CloudLimitError as exc:
            raise CloudAIError("cloud_request_limit") from exc
        except (OSError, sqlite3.Error) as exc:
            raise CloudAIError("cloud_usage_store_unavailable") from exc
        try:
            with httpx.Client(
                timeout=self.settings.QWEN_TIMEOUT_SECONDS,
                follow_redirects=False,
                trust_env=False,
                transport=self.transport,
            ) as client:
                with client.stream(
                    "POST",
                    self.base_url + "/chat/completions",
                    json=payload,
                    headers={
                        "Authorization": "Bearer "
                        + self.settings.DASHSCOPE_API_KEY.get_secret_value()
                    },
                ) as response:
                    if response.status_code != 200:
                        code = {
                            401: "cloud_auth_failed",
                            403: "cloud_access_denied",
                            429: "cloud_rate_limited",
                        }.get(response.status_code, "cloud_http_error")
                        raise CloudAIError(code, attempted=True)
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > MAX_RESPONSE_BYTES:
                            raise CloudAIError("cloud_response_too_large", attempted=True)
            data = json.loads(body)
            if not isinstance(data, dict) or data.get("error"):
                raise CloudAIError("cloud_invalid_response", attempted=True)
            choices = data.get("choices")
            if not isinstance(choices, list) or len(choices) != 1:
                raise CloudAIError("cloud_invalid_response", attempted=True)
            choice = choices[0]
            if not isinstance(choice, dict):
                raise CloudAIError("cloud_invalid_response", attempted=True)
            if choice.get("finish_reason") != "stop":
                raise CloudAIError("cloud_incomplete_response", attempted=True)
            message = choice.get("message")
            if not isinstance(message, dict) or message.get("role", "assistant") != "assistant":
                raise CloudAIError("cloud_invalid_response", attempted=True)
            refusal = message.get("refusal")
            if refusal is not None and refusal != "":
                raise CloudAIError("cloud_refusal_response", attempted=True)
            if (
                message.get("tool_calls") is not None and message["tool_calls"] != []
                or message.get("function_call") is not None
            ):
                raise CloudAIError("cloud_unexpected_tool_response", attempted=True)
            content = message.get("content")
            if not isinstance(content, str) or not content.strip():
                raise CloudAIError("cloud_empty_response", attempted=True)
            usage = data.get("usage") or {}
            safe_usage = {
                name: value
                for name in ("prompt_tokens", "completion_tokens", "total_tokens")
                if type(value := usage.get(name)) is int and value >= 0
            }
            return content, {"provider": "qwen", "model": model, **safe_usage}
        except httpx.TimeoutException as exc:
            raise CloudAIError("cloud_timeout", attempted=True) from exc
        except httpx.HTTPError as exc:
            raise CloudAIError("cloud_network_error", attempted=True) from exc
        except (ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
            raise CloudAIError("cloud_invalid_response", attempted=True) from exc
