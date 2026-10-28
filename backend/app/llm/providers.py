from typing import Protocol

from pydantic import BaseModel, Field

from backend.app.llm.errors import LLMConfigurationError
from backend.app.llm.source_grounding import SourceContextItem


class LLMProviderMetadata(BaseModel):
    provider_name: str
    model_name: str
    enabled: bool = False
    supports_network: bool = False
    safety_mode: str = "offline"


class LLMGenerationRequest(BaseModel):
    system_prompt: str
    user_prompt: str
    source_context: list[SourceContextItem] = Field(default_factory=list)
    scenario: str | None = None
    risk_level: str | None = None
    language: str | None = None
    max_tokens: int | None = Field(default=None, gt=0)


class LLMGenerationResult(BaseModel):
    text: str
    provider_name: str
    model_name: str
    used_provider_call: bool
    safety_mode: str
    finish_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)


class GroundedLLMProvider(Protocol):
    provider_name: str
    model_name: str

    def metadata(self) -> LLMProviderMetadata:
        """Return provider metadata without making a provider call."""

    def generate(self, request: LLMGenerationRequest) -> LLMGenerationResult:
        """Generate grounded answer text from a normalized generation request."""


class FakeLLMProvider:
    provider_name = "fake"

    def __init__(self, model_name: str = "fake-grounded-llm") -> None:
        self.model_name = model_name

    def metadata(self) -> LLMProviderMetadata:
        return LLMProviderMetadata(
            provider_name=self.provider_name,
            model_name=self.model_name,
            enabled=True,
            supports_network=False,
            safety_mode="offline_fake",
        )

    def generate(self, request: LLMGenerationRequest) -> LLMGenerationResult:
        source_ids = [source.source_id for source in request.source_context]
        source_text = ", ".join(source_ids) if source_ids else "none"
        scenario = request.scenario or "unspecified"
        risk_level = request.risk_level or "unspecified"
        language = request.language or "unspecified"
        text = "\n".join(
            [
                "Direct short answer",
                (
                    "Fake offline provider response for tests only. It does not call a "
                    "real LLM provider and must not be treated as production advice."
                ),
                "",
                "Source-grounded facts",
                f"Source context received: {source_text}.",
                "",
                "Practical next steps",
                (
                    "Use official or curated sources for factual requirements and keep "
                    "community content as practical context only."
                ),
                "",
                "Unverified or uncertain points",
                "Current official details still require verification before action.",
                "",
                "When to escalate",
                (
                    "Escalate high-risk legal, work-status, medical, document, or emergency "
                    "cases to official or qualified human help."
                ),
                "",
                "Source notes",
                (
                    f"scenario={scenario}; risk_level={risk_level}; language={language}; "
                    f"max_tokens={request.max_tokens or 'default'}."
                ),
            ]
        )
        return LLMGenerationResult(
            text=text,
            provider_name=self.provider_name,
            model_name=self.model_name,
            used_provider_call=False,
            safety_mode="offline_fake",
            finish_reason="stop",
            warnings=[
                "FakeLLMProvider used; no network or real provider call was made.",
                "Output is deterministic test-safe text, not production LLM generation.",
            ],
        )


class GuardedRealLLMProvider:
    def __init__(
        self,
        provider_name: str,
        model_name: str,
        enabled: bool = False,
    ) -> None:
        self.provider_name = provider_name
        self.model_name = model_name
        self.enabled = enabled

    def metadata(self) -> LLMProviderMetadata:
        return LLMProviderMetadata(
            provider_name=self.provider_name,
            model_name=self.model_name,
            enabled=self.enabled,
            supports_network=False,
            safety_mode="guarded_placeholder",
        )

    def generate(self, request: LLMGenerationRequest) -> LLMGenerationResult:
        del request
        if not self.enabled:
            raise LLMConfigurationError(
                f"LLM provider '{self.provider_name}' is disabled. Phase 40 defaults "
                "to fake offline generation and does not allow real provider calls."
            )
        raise LLMConfigurationError(
            f"LLM provider '{self.provider_name}' is only a guarded placeholder in Phase 40; "
            "real network generation is not implemented."
        )
