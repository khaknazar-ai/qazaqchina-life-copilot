"""Runtime wiring for the opt-in Singapore retrieval providers."""

from pathlib import Path

import httpx

from backend.app.cloud_ai.budget import CloudRequestBudget
from backend.app.cloud_ai.client import PROJECT_ROOT, validate_cloud_settings
from backend.app.config import Settings
from backend.app.embeddings.models import EmbeddingProviderConfig
from backend.app.hybrid_retrieval.cloud import CloudHybridRetrievalService
from backend.app.reranking.models import RerankingProviderConfig
from backend.app.source_registry.registry import SourceRegistry


def build_cloud_retrieval(
    settings: Settings, registry: SourceRegistry, *, transport: httpx.BaseTransport | None = None,
) -> CloudHybridRetrievalService:
    if not settings.CLOUD_RETRIEVAL_ENABLED:
        raise ValueError("Cloud retrieval is disabled")
    endpoint = validate_cloud_settings(settings)
    directory = (PROJECT_ROOT / Path(settings.LOCAL_DATA_DIR)).resolve()
    if not directory.is_relative_to(PROJECT_ROOT):
        raise ValueError("Cloud retrieval storage must stay inside the repository")
    budget = CloudRequestBudget(
        directory / "cloud_usage.sqlite3",
        settings.QWEN_DAILY_REQUEST_LIMIT, settings.QWEN_REQUESTS_PER_MINUTE,
    )
    return CloudHybridRetrievalService(
        source_registry=registry,
        embedding_config=EmbeddingProviderConfig(
            provider="qwen", model=settings.QWEN_EMBEDDING_MODEL,
            dimensions=settings.QWEN_EMBEDDING_DIMENSIONS,
            enabled=True, allow_external=True, base_url=endpoint,
            api_key=settings.DASHSCOPE_API_KEY,
            timeout_seconds=settings.QWEN_TIMEOUT_SECONDS, max_attempts=1,
        ),
        reranking_config=RerankingProviderConfig(
            model=settings.QWEN_RERANK_MODEL, enabled=settings.QWEN_RERANK_ENABLED,
            allow_external=settings.QWEN_RERANK_ENABLED, base_url=endpoint,
            api_key=settings.DASHSCOPE_API_KEY,
            timeout_seconds=settings.QWEN_TIMEOUT_SECONDS, max_attempts=1,
        ),
        index_path=directory / "retrieval_vectors.sqlite3", budget=budget, transport=transport,
    )
