from pydantic import BaseModel, Field

from backend.app.config import Settings


class LLMProviderServiceConfig(BaseModel):
    provider_name: str = "fake"
    model_name: str = "fake-grounded-llm"
    enabled: bool = False
    default_max_tokens: int = Field(default=600, gt=0)


def llm_provider_service_config_from_settings(
    settings: Settings,
) -> LLMProviderServiceConfig:
    return LLMProviderServiceConfig(
        provider_name=settings.LLM_PROVIDER,
        model_name=settings.LLM_PROVIDER_MODEL,
        enabled=settings.LLM_PROVIDER_ENABLED,
        default_max_tokens=settings.LLM_GENERATION_MAX_TOKENS,
    )
