from backend.app.config import Settings, get_settings
from backend.app.core.providers import LLMProvider, MockLLMProvider


def get_llm_provider(settings: Settings | None = None) -> LLMProvider:
    active_settings = settings or get_settings()
    provider_name = active_settings.LLM_DEFAULT_PROVIDER.lower()

    if provider_name == "mock":
        return MockLLMProvider(model=active_settings.LLM_DEFAULT_MODEL)

    raise ValueError(
        f"LLM provider '{active_settings.LLM_DEFAULT_PROVIDER}' is not implemented in Phase 1. "
        "Only 'mock' is available."
    )
