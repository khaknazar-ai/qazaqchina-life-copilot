from collections.abc import Sequence
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class LLMMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class LLMResponse(BaseModel):
    provider: str
    model: str
    text: str
    token_usage: dict[str, int] = Field(default_factory=dict)


@runtime_checkable
class LLMProvider(Protocol):
    provider: str
    model: str

    def generate(self, messages: Sequence[LLMMessage]) -> LLMResponse:
        """Generate a response from a list of messages."""


class MockLLMProvider:
    provider = "mock"

    def __init__(self, model: str = "mock-basic") -> None:
        self.model = model

    def generate(self, messages: Sequence[LLMMessage]) -> LLMResponse:
        prompt_tokens = sum(len(message.content.split()) for message in messages)
        text = (
            f"This is a deterministic mock response from {self.provider}/{self.model}. "
            "No external AI provider was called."
        )
        completion_tokens = len(text.split())

        return LLMResponse(
            provider=self.provider,
            model=self.model,
            text=text,
            token_usage={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        )
