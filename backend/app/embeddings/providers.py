from hashlib import sha256
from typing import Protocol

import httpx

from backend.app.cloud_ai.budget import CloudRequestBudget
from backend.app.embeddings.models import (
    EmbeddingProviderConfig,
    EmbeddingRequest,
    EmbeddingResponse,
)


class EmbeddingProvider(Protocol):
    def embed_texts(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Embed text strings without writing vector indexes."""


class FakeEmbeddingProvider:
    provider = "fake"

    def embed_texts(self, request: EmbeddingRequest) -> EmbeddingResponse:
        if request.provider != self.provider:
            raise ValueError("FakeEmbeddingProvider only accepts provider='fake'.")
        dimensions = _validated_dimensions(request.dimensions)
        return EmbeddingResponse(
            vectors=[_fake_vector(text, dimensions) for text in request.texts],
            provider=self.provider,
            model=request.model,
            dimensions=dimensions,
            used_network=False,
            used_external_provider=False,
            warnings=[
                "FakeEmbeddingProvider used; no network or external embedding model was called.",
                "Vectors are deterministic hash fixtures for adapter testing only.",
            ],
        )


def create_embedding_provider(
    config: EmbeddingProviderConfig | None = None,
    *, budget: CloudRequestBudget | None = None,
    transport: httpx.BaseTransport | None = None,
) -> EmbeddingProvider:
    active_config = config or EmbeddingProviderConfig()
    if not active_config.enabled:
        raise ValueError("Embedding provider is disabled by configuration.")
    if active_config.provider == "qwen":
        from backend.app.embeddings.qwen import QwenEmbeddingProvider

        if budget is None:
            raise ValueError("External embeddings require a shared request budget.")
        return QwenEmbeddingProvider(active_config, budget=budget, transport=transport)
    if active_config.provider != "fake":
        raise ValueError(
            "Only the fake embedding provider and explicitly enabled qwen provider are available."
        )
    if active_config.allow_external:
        raise ValueError(
            "External embedding providers are disabled in Phase 55 and must not be called."
        )
    _validated_dimensions(active_config.dimensions)
    return FakeEmbeddingProvider()


def _fake_vector(text: str, dimensions: int) -> list[float]:
    normalized = " ".join(text.split())
    seed = f"fake-hash-embedding-v1::{normalized}".encode()
    values: list[float] = []
    counter = 0
    while len(values) < dimensions:
        digest = sha256(seed + f"::{counter}".encode()).digest()
        for offset in range(0, len(digest), 4):
            if len(values) >= dimensions:
                break
            integer = int.from_bytes(digest[offset : offset + 4], "big", signed=False)
            values.append(round((integer / 4_294_967_295) * 2 - 1, 6))
        counter += 1
    return values


def _validated_dimensions(dimensions: int) -> int:
    if dimensions <= 0:
        raise ValueError("Embedding dimensions must be greater than zero.")
    return dimensions
