from typing import Any

import httpx

from backend.app.llm.errors import (
    LLMConfigurationError,
    LLMRequestError,
    LLMResponseError,
)
from backend.app.llm.models import LLMProviderConfig, LLMRequest, LLMResponse, LLMUsage


class OpenAICompatibleChatProvider:
    def __init__(
        self,
        config: LLMProviderConfig,
        http_client: object | None = None,
    ) -> None:
        self.config = config
        self.http_client = http_client
        self.provider_name = config.provider
        self.model_name = config.model

    def generate(self, request: LLMRequest) -> LLMResponse:
        self._validate_config()
        payload = self._payload(request)
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

        try:
            if self.http_client is not None:
                response = self.http_client.post(
                    self._chat_completions_url(),
                    json=payload,
                    headers=headers,
                    timeout=self.config.timeout_seconds,
                )
            else:
                with httpx.Client(timeout=self.config.timeout_seconds) as client:
                    response = client.post(
                        self._chat_completions_url(),
                        json=payload,
                        headers=headers,
                    )
        except httpx.HTTPError as exc:
            raise LLMRequestError(
                f"LLM provider request failed for provider '{self.provider_name}'."
            ) from exc

        if response.status_code < 200 or response.status_code >= 300:
            raise LLMRequestError(
                "LLM provider request failed with status "
                f"{response.status_code} for provider '{self.provider_name}'."
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise LLMResponseError(
                f"LLM provider '{self.provider_name}' returned invalid JSON."
            ) from exc

        return self._parse_response(data, request)

    def _validate_config(self) -> None:
        if not self.config.enabled:
            raise LLMConfigurationError(
                f"LLM provider '{self.provider_name}' is disabled."
            )
        if not self.config.api_key:
            raise LLMConfigurationError(
                f"LLM provider '{self.provider_name}' requires an API key."
            )
        if not self.config.base_url:
            raise LLMConfigurationError(
                f"LLM provider '{self.provider_name}' requires a base URL."
            )

    def _payload(self, request: LLMRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.model or self.model_name,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in request.messages
            ],
            "temperature": request.temperature,
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        return payload

    def _chat_completions_url(self) -> str:
        base_url = (self.config.base_url or "").rstrip("/")
        if base_url.casefold().endswith("/chat/completions"):
            return base_url
        return f"{base_url}/chat/completions"

    def _parse_response(self, data: dict[str, Any], request: LLMRequest) -> LLMResponse:
        try:
            first_choice = data["choices"][0]
            content = first_choice["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMResponseError(
                f"LLM provider '{self.provider_name}' returned a malformed response."
            ) from exc

        if not isinstance(content, str):
            raise LLMResponseError(
                f"LLM provider '{self.provider_name}' returned non-text content."
            )

        usage = data.get("usage") or {}
        return LLMResponse(
            content=content,
            provider=self.provider_name,
            model=str(data.get("model") or request.model or self.model_name),
            usage=LLMUsage(
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
                total_tokens=usage.get("total_tokens"),
            ),
            raw_response=data,
            finish_reason=first_choice.get("finish_reason"),
        )
