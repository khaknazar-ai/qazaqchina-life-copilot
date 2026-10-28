"""Alibaba OpenAI-compatible dense embeddings without an SDK dependency."""

import math

import httpx

from backend.app.cloud_ai.budget import CloudRequestBudget
from backend.app.embeddings.cloud_http import RetrievalHTTPClient, RetrievalProviderError
from backend.app.embeddings.models import (
    EmbeddingProviderConfig,
    EmbeddingRequest,
    EmbeddingResponse,
)
from backend.app.embeddings.safety import safe_external_text

SUPPORTED_DIMENSIONS = {64, 128, 256, 512, 768, 1024, 1536, 2048}


class QwenEmbeddingProvider:
    provider = "qwen"

    def __init__(
        self,
        config: EmbeddingProviderConfig,
        *,
        budget: CloudRequestBudget,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if (
            not config.enabled
            or not config.allow_external
            or config.provider != "qwen"
            or config.model != "text-embedding-v4"
            or config.dimensions not in SUPPORTED_DIMENSIONS
        ):
            raise RetrievalProviderError("retrieval_configuration_invalid")
        self.config = config
        self.client = RetrievalHTTPClient(
            base_url=config.base_url,
            api_key=config.api_key,
            budget=budget,
            timeout_seconds=config.timeout_seconds,
            max_attempts=config.max_attempts,
            transport=transport,
        )

    def embed_texts(self, request: EmbeddingRequest) -> EmbeddingResponse:
        if (
            request.provider != self.provider
            or request.model != self.config.model
            or request.dimensions != self.config.dimensions
            or not 1 <= len(request.texts) <= 10
        ):
            raise RetrievalProviderError("retrieval_input_invalid")
        texts = [safe_external_text(text) for text in request.texts]
        # UTF-8 bytes conservatively bound the token count without downloading a
        # tokenizer. Document chunks are far below the provider's token limit.
        if any(len(text.encode("utf-8")) > 8192 for text in texts):
            raise RetrievalProviderError("retrieval_input_too_large")
        result = self.client.post(
            "/embeddings",
            {
                "model": self.config.model,
                "input": texts,
                "dimensions": self.config.dimensions,
                "encoding_format": "float",
            },
            kind="embedding",
        )
        if result.get("model") != self.config.model or result.get("object") != "list":
            raise self._invalid()
        data = result.get("data")
        if not isinstance(data, list) or len(data) != len(texts):
            raise self._invalid()
        ordered: dict[int, list[float]] = {}
        for item in data:
            if not isinstance(item, dict):
                raise self._invalid()
            index, vector = item.get("index"), item.get("embedding")
            if (
                type(index) is not int
                or not 0 <= index < len(texts)
                or index in ordered
                or item.get("object") != "embedding"
                or not valid_vector(vector, self.config.dimensions)
            ):
                raise self._invalid()
            ordered[index] = [float(value) for value in vector]
        return EmbeddingResponse(
            vectors=[ordered[index] for index in range(len(texts))],
            provider=self.provider,
            model=self.config.model,
            dimensions=self.config.dimensions,
            used_network=True,
            used_external_provider=True,
            provider_calls=self.client.last_attempts,
        )

    def _invalid(self) -> RetrievalProviderError:
        return RetrievalProviderError(
            "retrieval_embedding_invalid",
            attempts=self.client.last_attempts,
        )


def valid_vector(vector: object, dimensions: int) -> bool:
    return (
        isinstance(vector, list)
        and len(vector) == dimensions
        and all(
            type(value) in {float, int} and math.isfinite(value) and abs(value) <= 1e6
            for value in vector
        )
        and any(value != 0 for value in vector)
    )
