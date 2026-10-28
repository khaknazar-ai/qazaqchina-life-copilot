from pydantic import BaseModel, Field


class CapabilitiesResponse(BaseModel):
    app_name: str
    environment: str
    default_llm_provider: str
    default_llm_model: str
    external_llm_enabled: bool
    local_persistence_enabled: bool
    supported_languages: list[str] = Field(default_factory=list)
    supported_scenarios: list[str] = Field(default_factory=list)
    supported_llm_providers: list[str] = Field(default_factory=list)
    feature_flags: dict[str, bool] = Field(default_factory=dict)
