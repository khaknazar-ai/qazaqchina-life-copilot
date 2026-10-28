from backend.app.llm.models import LLMProviderConfig, LLMRequest, LLMResponse, LLMUsage


class MockLLMProvider:
    provider_name = "mock"

    def __init__(
        self,
        model: str = "mock-qazaqchina-local",
        config: LLMProviderConfig | None = None,
    ) -> None:
        self.config = config or LLMProviderConfig(
            provider=self.provider_name,
            model=model,
            enabled=True,
        )
        self.model_name = self.config.model

    def generate(self, request: LLMRequest) -> LLMResponse:
        prompt_tokens = sum(len(message.content.split()) for message in request.messages)
        user_message = _last_user_message(request)
        content = (
            f"This is a deterministic mock response from {self.provider_name}/"
            f"{self.model_name}. No external AI provider was called. "
            f"Last user message length: {len(user_message)}."
        )
        completion_tokens = len(content.split())

        return LLMResponse(
            content=content,
            provider=self.provider_name,
            model=request.model or self.model_name,
            usage=LLMUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
                estimated_cost_usd=0.0,
            ),
            finish_reason="stop",
        )


def _last_user_message(request: LLMRequest) -> str:
    for message in reversed(request.messages):
        if message.role == "user":
            return message.content
    return request.messages[-1].content if request.messages else ""
