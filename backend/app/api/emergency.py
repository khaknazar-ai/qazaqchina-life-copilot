from typing import Annotated

from fastapi import APIRouter, Depends

from backend.app.api.dependencies import get_trace_service
from backend.app.schemas.emergency import EmergencyHelpRequest, EmergencyHelpResponse
from backend.app.services.emergency_service import EmergencyService
from backend.app.services.trace_service import TraceService

router = APIRouter(prefix="/api", tags=["emergency"])


@router.post("/emergency/help", response_model=EmergencyHelpResponse)
def emergency_help(
    request: EmergencyHelpRequest,
    trace_service: Annotated[TraceService, Depends(get_trace_service)],
) -> EmergencyHelpResponse:
    return EmergencyService(trace_service=trace_service).create_help_response(request)
