from typing import Any

from backend.app.config import Settings
from backend.app.llm.base import LLMProvider
from backend.app.llm.errors import LLMConfigurationError
from backend.app.llm.mock import MockLLMProvider
from backend.app.llm.models import LLMProviderConfig
from backend.app.llm.openai_compatible import OpenAICompatibleChatProvider

SUPPORTED_PROVIDERS = ["mock", "openai", "deepseek", "openrouter"]
OPENAI_COMPATIBLE_PROVIDERS = {"openai", "deepseek", "openrouter"}


def build_llm_provider(config: LLMProviderConfig) -> LLMProvider:
    provider_name = config.provider.casefold()
    if provider_name == "mock":
        return MockLLMProvider(config=config.model_copy(update={"enabled": True}))
    if provider_name in OPENAI_COMPATIBLE_PROVIDERS:
        return OpenAICompatibleChatProvider(config=config)
    raise LLMConfigurationError(f"Unsupported LLM provider '{config.provider}'.")


def provider_config_from_settings(settings: Settings) -> LLMProviderConfig:
    provider_name = settings.LLM_DEFAULT_PROVIDER.casefold()
    return LLMProviderConfig(
        provider=provider_name,
        model=settings.LLM_DEFAULT_MODEL,
        base_url=_base_url_for_provider(provider_name, settings),
        api_key=_none_if_blank(settings.LLM_API_KEY),
        timeout_seconds=settings.LLM_TIMEOUT_SECONDS,
        enabled=True if provider_name == "mock" else settings.LLM_ENABLE_EXTERNAL,
    )


def supported_providers() -> list[str]:
    return list(SUPPORTED_PROVIDERS)


def _base_url_for_provider(provider_name: str, settings: Settings) -> str | None:
    if settings.LLM_BASE_URL:
        return settings.LLM_BASE_URL

    provider_base_urls: dict[str, Any] = {
        "openai": settings.OPENAI_BASE_URL,
        "deepseek": settings.DEEPSEEK_BASE_URL,
        "openrouter": settings.OPENROUTER_BASE_URL,
    }
    return _none_if_blank(provider_base_urls.get(provider_name))


def _none_if_blank(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None
