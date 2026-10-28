from typing import Any

from pydantic import BaseModel, Field


class LLMMessage(BaseModel):
    role: str
    content: str


class LLMRequest(BaseModel):
    messages: list[LLMMessage]
    model: str | None = None
    temperature: float = 0.0
    max_tokens: int | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


class LLMUsage(BaseModel):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    estimated_cost_usd: float | None = None


class LLMResponse(BaseModel):
    content: str
    provider: str
    model: str
    usage: LLMUsage = Field(default_factory=LLMUsage)
    raw_response: dict[str, Any] | None = None
    finish_reason: str | None = None

    def trace_metadata(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "prompt_tokens": self.usage.prompt_tokens,
            "completion_tokens": self.usage.completion_tokens,
            "total_tokens": self.usage.total_tokens,
            "estimated_cost_usd": self.usage.estimated_cost_usd,
        }


class LLMProviderConfig(BaseModel):
    provider: str
    model: str
    base_url: str | None = None
    api_key: str | None = Field(default=None, repr=False)
    timeout_seconds: float = 30.0
    enabled: bool = False

    def safe_metadata(self) -> dict[str, str | float | bool | None]:
        return {
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "timeout_seconds": self.timeout_seconds,
            "enabled": self.enabled,
        }
