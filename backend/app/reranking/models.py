from pydantic import BaseModel, Field, SecretStr


class RerankingProviderConfig(BaseModel):
    model: str = "qwen3-rerank"
    enabled: bool = False
    allow_external: bool = False
    base_url: str | None = None
    api_key: SecretStr | None = Field(default=None, exclude=True, repr=False)
    timeout_seconds: float = Field(default=30, ge=1, le=60)
    max_attempts: int = Field(default=2, ge=1, le=2)


class RerankingResult(BaseModel):
    scores: dict[int, float]
    model: str
    provider_calls: int = 0
    used_network: bool = False
