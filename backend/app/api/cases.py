from typing import Annotated

from fastapi import APIRouter, Depends, Request

from backend.app.admin_auth.dependencies import require_admin_permission
from backend.app.admin_auth.permissions import PERMISSION_ADMIN_READ
from backend.app.api.dependencies import get_case_service
from backend.app.api_utils.pilot_access import bind_citizen_request
from backend.app.schemas.cases import CaseCreateRequest, CaseListResponse, CaseResponse
from backend.app.services.case_service import CaseService

router = APIRouter(prefix="/api", tags=["cases"])


@router.post("/cases", response_model=CaseResponse)
def create_case(
    request: CaseCreateRequest,
    http_request: Request,
    service: Annotated[CaseService, Depends(get_case_service)],
) -> CaseResponse:
    return service.create_case(bind_citizen_request(http_request, request))


@router.get(
    "/cases",
    response_model=CaseListResponse,
    dependencies=[Depends(require_admin_permission(PERMISSION_ADMIN_READ))],
)
def list_cases(
    service: Annotated[CaseService, Depends(get_case_service)],
) -> CaseListResponse:
    return service.list_cases()
