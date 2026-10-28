from typing import Annotated

from fastapi import APIRouter, Depends

from backend.app.api.dependencies import get_source_registry, get_trace_service
from backend.app.schemas.sources import CommunitySourceListResponse, SourceListResponse
from backend.app.services.source_service import SourceService
from backend.app.services.trace_service import TraceService
from backend.app.source_registry.registry import SourceRegistry

router = APIRouter(prefix="/api", tags=["sources"])


@router.get("/sources", response_model=SourceListResponse)
def list_sources(
    trace_service: Annotated[TraceService, Depends(get_trace_service)],
    registry: Annotated[SourceRegistry, Depends(get_source_registry)],
) -> SourceListResponse:
    return SourceService(trace_service=trace_service, source_registry=registry).list_sources()


@router.get("/sources/community", response_model=CommunitySourceListResponse)
def list_community_sources(
    trace_service: Annotated[TraceService, Depends(get_trace_service)],
    registry: Annotated[SourceRegistry, Depends(get_source_registry)],
) -> CommunitySourceListResponse:
    service = SourceService(trace_service=trace_service, source_registry=registry)
    return service.list_community_sources()
