"""Qwen3 reranking: only scores and original input indices are accepted."""

import math

import httpx

from backend.app.cloud_ai.budget import CloudRequestBudget
from backend.app.embeddings.cloud_http import (
    RERANK_PATH,
    RetrievalHTTPClient,
    RetrievalProviderError,
)
from backend.app.embeddings.safety import safe_external_text
from backend.app.reranking.models import RerankingProviderConfig, RerankingResult


class QwenRerankingProvider:
    def __init__(
        self,
        config: RerankingProviderConfig,
        *,
        budget: CloudRequestBudget,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not config.enabled or not config.allow_external or config.model != "qwen3-rerank":
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

    def rerank(self, query: str, documents: list[str]) -> RerankingResult:
        if not 1 <= len(documents) <= 32:
            raise RetrievalProviderError("retrieval_input_invalid")
        safe_query = safe_external_text(query, max_chars=1500)
        safe_documents = [safe_external_text(text, max_chars=2400) for text in documents]
        if len(safe_query.encode("utf-8")) > 2000 or any(
            len(text.encode("utf-8")) > 8000 for text in safe_documents
        ):
            raise RetrievalProviderError("retrieval_input_too_large")
        result = self.client.post(
            RERANK_PATH,
            {
                "model": self.config.model,
                "input": {"query": safe_query, "documents": safe_documents},
                "parameters": {"top_n": len(documents), "return_documents": False},
            },
            kind="rerank",
        )
        output = result.get("output")
        results = output.get("results") if isinstance(output, dict) else None
        if (
            "model" in result and result["model"] != self.config.model
            or not isinstance(results, list)
        ):
            raise self._invalid()
        if len(results) != len(documents):
            raise self._invalid()
        scores: dict[int, float] = {}
        for item in results:
            if not isinstance(item, dict):
                raise self._invalid()
            index, score = item.get("index"), item.get("relevance_score")
            if (
                type(index) is not int
                or not 0 <= index < len(documents)
                or index in scores
                or type(score) not in {int, float}
                or not math.isfinite(score)
                or not 0 <= score <= 1
            ):
                raise self._invalid()
            scores[index] = float(score)
        return RerankingResult(
            scores=scores,
            model=self.config.model,
            used_network=True,
            provider_calls=self.client.last_attempts,
        )

    def _invalid(self) -> RetrievalProviderError:
        return RetrievalProviderError(
            "retrieval_rerank_invalid", attempts=self.client.last_attempts
        )
