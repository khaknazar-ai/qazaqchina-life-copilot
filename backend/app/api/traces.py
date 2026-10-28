from typing import Annotated

from fastapi import APIRouter, Depends

from backend.app.admin_auth.dependencies import require_admin_permission
from backend.app.admin_auth.permissions import PERMISSION_AUDIT_READ
from backend.app.api.dependencies import get_trace_service
from backend.app.schemas.traces import TraceListResponse
from backend.app.services.trace_service import TraceService

router = APIRouter(prefix="/api", tags=["traces"])


@router.get(
    "/traces",
    response_model=TraceListResponse,
    dependencies=[Depends(require_admin_permission(PERMISSION_AUDIT_READ))],
)
def list_traces(
    trace_service: Annotated[TraceService, Depends(get_trace_service)],
) -> TraceListResponse:
    return TraceListResponse(events=trace_service.read_events())
