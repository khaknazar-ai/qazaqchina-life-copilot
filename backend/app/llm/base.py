from typing import Protocol

from backend.app.llm.models import LLMRequest, LLMResponse


class LLMProvider(Protocol):
    provider_name: str
    model_name: str

    def generate(self, request: LLMRequest) -> LLMResponse:
        """Generate a response from a provider-specific backend."""
