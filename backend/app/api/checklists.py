from typing import Annotated

from fastapi import APIRouter, Depends

from backend.app.api.dependencies import get_trace_service
from backend.app.schemas.checklists import ChecklistCreateRequest, ChecklistResponse
from backend.app.services.checklist_service import ChecklistService
from backend.app.services.trace_service import TraceService

router = APIRouter(prefix="/api", tags=["checklists"])


@router.post("/checklists", response_model=ChecklistResponse)
def create_checklist(
    request: ChecklistCreateRequest,
    trace_service: Annotated[TraceService, Depends(get_trace_service)],
) -> ChecklistResponse:
    return ChecklistService(trace_service=trace_service).create_checklist(request)
