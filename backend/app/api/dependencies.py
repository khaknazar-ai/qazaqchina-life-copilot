import sqlite3
from typing import Annotated

from fastapi import Depends, HTTPException, Request

from backend.app.cloud_ai.client import QwenCloudClient
from backend.app.config import Settings, get_settings
from backend.app.memory.service import SessionMemoryService
from backend.app.moderation.service import CommunityModerationService
from backend.app.persistence.factory import (
    build_case_repository,
    build_community_post_repository,
    build_local_record_store,
)
from backend.app.persistence.runtime_sources import build_runtime_source_registry
from backend.app.services.case_service import CaseService
from backend.app.services.community_service import CommunityService
from backend.app.services.trace_service import TraceService
from backend.app.source_registry.registry import SourceRegistry


def get_trace_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> TraceService:
    return TraceService(trace_dir=settings.TRACE_DIR)


def get_case_service(
    settings: Annotated[Settings, Depends(get_settings)],
    trace_service: Annotated[TraceService, Depends(get_trace_service)],
) -> CaseService:
    return CaseService(
        trace_service=trace_service,
        case_repository=(
            build_case_repository(settings.LOCAL_DATA_DIR)
            if settings.ENABLE_LOCAL_PERSISTENCE
            else None
        ),
    )


def get_community_service(
    settings: Annotated[Settings, Depends(get_settings)],
    trace_service: Annotated[TraceService, Depends(get_trace_service)],
) -> CommunityService:
    return CommunityService(
        trace_service=trace_service,
        moderation_service=CommunityModerationService(),
        post_repository=(
            build_community_post_repository(settings.LOCAL_DATA_DIR)
            if settings.ENABLE_LOCAL_PERSISTENCE
            else None
        ),
    )


def get_session_memory_service(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> SessionMemoryService:
    service = getattr(request.app.state, "session_memory_service", None)
    if service is None:
        service = SessionMemoryService(
            repository=(
                build_local_record_store(settings.LOCAL_DATA_DIR, "session_memory.jsonl")
                if settings.ENABLE_LOCAL_PERSISTENCE
                else None
            )
        )
        request.app.state.session_memory_service = service
    return service


def get_source_registry(
    settings: Annotated[Settings, Depends(get_settings)],
    request: Request,
) -> SourceRegistry:
    try:
        registry = build_runtime_source_registry(
            settings,
            getattr(request.app.state, "source_corpus_service", None),
        )
    except (ValueError, OSError, TypeError, KeyError, sqlite3.Error):
        raise HTTPException(503, "Reviewed source storage is unavailable") from None
    if settings.CLOUD_RETRIEVAL_ENABLED:
        from backend.app.cloud_ai.retrieval_runtime import build_cloud_retrieval

        service = build_cloud_retrieval(settings, registry)
        return service.eligible_source_registry()
    return registry


def get_cloud_client(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> QwenCloudClient | None:
    if not (settings.QWEN_CHAT_ENABLED or settings.QWEN_OCR_ENABLED):
        return None
    client = getattr(request.app.state, "cloud_client", None)
    if client is None:
        client = QwenCloudClient(settings)
        request.app.state.cloud_client = client
    return client
