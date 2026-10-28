from backend.app.config import Settings, get_settings
from backend.app.llm.config import (
    LLMProviderServiceConfig,
    llm_provider_service_config_from_settings,
)
from backend.app.llm.providers import (
    FakeLLMProvider,
    GroundedLLMProvider,
    GuardedRealLLMProvider,
    LLMGenerationRequest,
    LLMGenerationResult,
)
from backend.app.llm.source_grounding import (
    SourceContextItem,
    build_grounded_prompt_pack,
)


class LLMGenerationService:
    def __init__(
        self,
        config: LLMProviderServiceConfig | None = None,
        provider: GroundedLLMProvider | None = None,
    ) -> None:
        self.config = config or LLMProviderServiceConfig()
        self.provider = provider or build_grounded_llm_provider(self.config)

    def build_generation_request(
        self,
        user_message: str,
        source_context: list[SourceContextItem] | None = None,
        scenario: str | None = None,
        risk_level: str | None = None,
        language: str | None = None,
        max_tokens: int | None = None,
    ) -> LLMGenerationRequest:
        prompt_pack = build_grounded_prompt_pack(
            user_message=user_message,
            source_context=source_context or [],
        )
        return LLMGenerationRequest(
            system_prompt=prompt_pack.system_prompt,
            user_prompt="\n\n".join([prompt_pack.context_block, prompt_pack.user_prompt]),
            source_context=source_context or [],
            scenario=scenario,
            risk_level=risk_level,
            language=language,
            max_tokens=max_tokens or self.config.default_max_tokens,
        )

    def generate(
        self,
        user_message: str,
        source_context: list[SourceContextItem] | None = None,
        scenario: str | None = None,
        risk_level: str | None = None,
        language: str | None = None,
        max_tokens: int | None = None,
    ) -> LLMGenerationResult:
        request = self.build_generation_request(
            user_message=user_message,
            source_context=source_context,
            scenario=scenario,
            risk_level=risk_level,
            language=language,
            max_tokens=max_tokens,
        )
        return self.provider.generate(request)


def build_grounded_llm_provider(config: LLMProviderServiceConfig) -> GroundedLLMProvider:
    provider_name = config.provider_name.casefold()
    if provider_name == "fake":
        return FakeLLMProvider(model_name=config.model_name)
    return GuardedRealLLMProvider(
        provider_name=config.provider_name,
        model_name=config.model_name,
        enabled=config.enabled,
    )


def build_llm_generation_service(
    settings: Settings | None = None,
    config: LLMProviderServiceConfig | None = None,
) -> LLMGenerationService:
    if config is not None:
        return LLMGenerationService(config=config)
    return LLMGenerationService(
        config=llm_provider_service_config_from_settings(settings or get_settings())
    )
