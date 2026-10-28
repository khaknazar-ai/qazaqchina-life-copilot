"""Opt-in local Ollama transport. No pulls, cloud fallback or tool execution."""

import json
import re
from threading import Lock
from urllib.parse import urlsplit

import httpx

from backend.app.cloud_ai.chat import CloudChatService
from backend.app.cloud_ai.client import CloudAIError
from backend.app.config import Settings

MAX_BYTES = 262144
MAX_INPUT_BYTES = 65536
_PROCESS_LOCK = Lock()


def validate_ollama_settings(settings: Settings) -> str:
    if not settings.OLLAMA_CHAT_ENABLED:
        return "disabled"
    if any(
        (
            settings.QWEN_CHAT_ENABLED,
            settings.QWEN_OCR_ENABLED,
            settings.CLOUD_RETRIEVAL_ENABLED,
            settings.QWEN_RERANK_ENABLED,
            settings.SEMANTIC_CONFLICT_REVIEW_ENABLED,
            settings.LLM_ENABLE_EXTERNAL,
        )
    ):
        raise CloudAIError("ollama_external_modes_conflict")
    try:
        url = urlsplit(settings.OLLAMA_BASE_URL)
        valid = (
            url.scheme == "http"
            and url.hostname in {"127.0.0.1", "::1"}
            and url.port is not None
            and 1 <= url.port <= 65535
            and url.path in {"", "/"}
            and not url.username
            and not url.password
            and not url.query
            and not url.fragment
        )
    except ValueError:
        valid = False
    if not valid:
        raise CloudAIError("ollama_endpoint_invalid")
    model = settings.OLLAMA_MODEL
    if (
        not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}", model)
        or "cloud" in model.casefold()
    ):
        raise CloudAIError("ollama_model_invalid")
    return settings.OLLAMA_BASE_URL.rstrip("/")


class OllamaGenerationError(CloudAIError):
    local_generation_attempted = True


class OllamaClient:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        self.settings = settings
        self.base_url = validate_ollama_settings(settings)
        self.transport = transport
        self._lock = _PROCESS_LOCK

    def _post(self, client: httpx.Client, path: str, payload: dict) -> dict:
        try:
            with client.stream("POST", self.base_url + path, json=payload) as response:
                if response.status_code != 200:
                    code = (
                        "ollama_model_unavailable"
                        if response.status_code == 404
                        else ("ollama_busy" if response.status_code == 429 else "ollama_http_error")
                    )
                    raise CloudAIError(code, attempted=True)
                if response.headers.get("content-encoding", "").strip().casefold() not in {
                    "",
                    "identity",
                }:
                    raise CloudAIError("ollama_compressed_response_rejected", attempted=True)
                body = bytearray()
                if response.is_stream_consumed:
                    # Preloaded test transports; real socket responses use bounded raw reads.
                    if len(response.content) > MAX_BYTES:
                        raise CloudAIError("ollama_response_too_large", attempted=True)
                    body.extend(response.content)
                else:
                    for chunk in response.iter_raw(chunk_size=8192):
                        if len(chunk) > MAX_BYTES - len(body):
                            raise CloudAIError("ollama_response_too_large", attempted=True)
                        body.extend(chunk)
            data = json.loads(body)
            if not isinstance(data, dict) or data.get("error"):
                raise CloudAIError("ollama_invalid_response", attempted=True)
            return data
        except httpx.TimeoutException:
            raise CloudAIError("ollama_timeout", attempted=True) from None
        except httpx.HTTPError:
            raise CloudAIError("ollama_connection_failed", attempted=True) from None
        except (ValueError, TypeError, RecursionError):
            raise CloudAIError("ollama_invalid_response", attempted=True) from None

    def complete(self, messages: list[dict], *, kind: str) -> tuple[str, dict]:
        if not self.settings.OLLAMA_CHAT_ENABLED or kind != "chat":
            raise CloudAIError("ollama_disabled")
        if validate_ollama_settings(self.settings) != self.base_url:
            raise CloudAIError("ollama_endpoint_changed")
        if len(json.dumps(messages, ensure_ascii=False).encode("utf-8")) > MAX_INPUT_BYTES:
            raise CloudAIError("ollama_input_too_large")
        if not self._lock.acquire(blocking=False):
            raise CloudAIError("ollama_busy")
        generation_attempted = False
        try:
            with httpx.Client(
                timeout=self.settings.OLLAMA_TIMEOUT_SECONDS,
                trust_env=False,
                follow_redirects=False,
                transport=self.transport,
                headers={"Accept-Encoding": "identity"},
            ) as client:
                info = self._post(client, "/api/show", {"model": self.settings.OLLAMA_MODEL})
                if (
                    info.get("remote_host")
                    or info.get("remote_model")
                    or not isinstance(info.get("model_info"), dict)
                    or not info["model_info"]
                ):
                    raise CloudAIError("ollama_local_model_required", attempted=True)
                generation_attempted = True
                data = self._post(
                    client,
                    "/api/chat",
                    {
                        "model": self.settings.OLLAMA_MODEL,
                        "messages": messages,
                        "stream": False,
                        "think": False,
                        "format": "json",
                        "keep_alive": "1m",
                        "options": {
                            "temperature": 0,
                            "num_ctx": self.settings.OLLAMA_CONTEXT_TOKENS,
                            "num_predict": self.settings.OLLAMA_MAX_TOKENS,
                        },
                    },
                )
            message = data.get("message")
            if (
                data.get("done") is not True
                or data.get("done_reason") != "stop"
                or not isinstance(message, dict)
                or message.get("role") != "assistant"
                or message.get("tool_calls")
                or message.get("function_call")
                or not isinstance(message.get("content"), str)
                or not message["content"].strip()
            ):
                raise CloudAIError("ollama_invalid_response", attempted=True)
            usage = {
                "provider": "ollama",
                "model": self.settings.OLLAMA_MODEL,
                "local_generation_attempted": True,
                "local_generation_completed": True,
            }
            for key, native in (
                ("prompt_tokens", "prompt_eval_count"),
                ("completion_tokens", "eval_count"),
            ):
                value = data.get(native)
                if type(value) is int and value >= 0:
                    usage[key] = value
            if "prompt_tokens" in usage and "completion_tokens" in usage:
                usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
            return message["content"], usage
        except CloudAIError as exc:
            if generation_attempted:
                raise OllamaGenerationError(exc.code, attempted=exc.attempted) from None
            raise
        finally:
            self._lock.release()


class OllamaChatService(CloudChatService):
    """Reuse citation, semantic review, freshness and publication checks unchanged."""

    def enrich(self, request, response, registry, *, context=None) -> None:
        from backend.app.cloud_ai.chat import _eligible_sources
        from backend.app.domain.enums import RiskLevel
        from backend.app.llm.conversation import LocalConversationService, conversation_mode

        mode = conversation_mode(
            request, response, context, has_sources=bool(_eligible_sources(response, registry))
        )
        if (
            isinstance(self.client, OllamaClient)
            and mode
            and response.risk_level
            not in {
                RiskLevel.emergency,
                RiskLevel.unsafe,
                RiskLevel.prompt_injection,
            }
        ):
            LocalConversationService(self.client).enrich(
                request, response, mode=mode, context=context
            )
        else:
            super().enrich(request, response, registry, context=context)
        # Compatibility field cloud_status is consumed by existing memory/delivery guards.
        response.metadata.update(
            inference_backend="ollama",
            ollama_status=response.metadata.get("cloud_status"),
            used_external_network=False,
            local_api_attempted=bool(response.metadata.get("used_provider_call")),
            local_generation_attempted=bool(response.metadata.get("local_generation_attempted")),
            local_generation_completed=bool(response.metadata.get("local_generation_completed")),
            used_local_inference=bool(response.metadata.get("local_generation_completed")),
        )
