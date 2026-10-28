from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from backend.app.admin_auth.dependencies import require_admin_permission
from backend.app.admin_auth.permissions import (
    PERMISSION_PRIVACY_DELETE_REQUEST_READ,
    PERMISSION_PRIVACY_DELETE_REQUEST_UPDATE,
    PERMISSION_PRIVACY_READ,
)
from backend.app.api_utils.pilot_access import bind_citizen_request
from backend.app.privacy.models import (
    DeleteRequestCreate,
    DeleteRequestRecord,
    DeleteRequestResponse,
    DeleteRequestStatus,
    PrivacyControlsSummary,
    RedactionResult,
    RetentionPolicy,
)
from backend.app.privacy.retention import default_retention_policies
from backend.app.privacy.service import PrivacyService

router = APIRouter(tags=["privacy"])
_PRIVACY_SERVICE = PrivacyService()


class RedactPreviewRequest(BaseModel):
    text: str


class PrivacyQueueUpdateRequest(BaseModel):
    status: DeleteRequestStatus
    note: str | None = None


@router.post("/api/privacy/delete-request", response_model=DeleteRequestResponse)
def create_delete_request(
    request: DeleteRequestCreate,
    http_request: Request,
) -> DeleteRequestResponse:
    try:
        return _get_service(http_request).create_delete_request(
            bind_citizen_request(http_request, request)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/privacy/policies", response_model=list[RetentionPolicy])
def privacy_policies() -> list[RetentionPolicy]:
    return default_retention_policies()


@router.post("/api/privacy/redact-preview", response_model=RedactionResult)
def redact_preview(
    request: RedactPreviewRequest,
    http_request: Request,
) -> RedactionResult:
    return _get_service(http_request).redact_text(request.text)


@router.get(
    "/api/admin/privacy/delete-requests",
    response_model=list[DeleteRequestRecord],
    dependencies=[Depends(require_admin_permission(PERMISSION_PRIVACY_DELETE_REQUEST_READ))],
)
def list_delete_requests(
    http_request: Request,
    status: DeleteRequestStatus | None = None,
    limit: int = 50,
) -> list[DeleteRequestRecord]:
    return _get_service(http_request).list_delete_requests(status=status, limit=limit)


@router.patch(
    "/api/admin/privacy/delete-requests/{request_id}",
    response_model=DeleteRequestRecord,
    dependencies=[Depends(require_admin_permission(PERMISSION_PRIVACY_DELETE_REQUEST_UPDATE))],
)
def update_delete_request(
    request_id: str,
    request: PrivacyQueueUpdateRequest,
    http_request: Request,
) -> DeleteRequestRecord:
    try:
        return _get_service(http_request).update_delete_request_status(
            request_id,
            request.status,
            request.note,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/api/admin/privacy/summary",
    response_model=PrivacyControlsSummary,
    dependencies=[Depends(require_admin_permission(PERMISSION_PRIVACY_READ))],
)
def privacy_summary(http_request: Request) -> PrivacyControlsSummary:
    return _get_service(http_request).summarize()


def reset_privacy_demo_state_for_tests() -> None:
    _PRIVACY_SERVICE.reset_for_tests()


def _get_service(request: Request) -> PrivacyService:
    service = getattr(request.app.state, "privacy_service", None)
    if isinstance(service, PrivacyService):
        return service
    return _PRIVACY_SERVICE
