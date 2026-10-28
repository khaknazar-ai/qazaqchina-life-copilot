class LLMProviderError(Exception):
    """Base error for LLM provider adapter failures."""


class LLMConfigurationError(LLMProviderError):
    """Raised when a provider is explicitly requested but not configured safely."""


class LLMRequestError(LLMProviderError):
    """Raised when a provider request fails before a usable response is available."""


class LLMResponseError(LLMProviderError):
    """Raised when a provider response cannot be parsed into the common model."""
