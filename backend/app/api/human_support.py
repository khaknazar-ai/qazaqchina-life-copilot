from fastapi import APIRouter, Depends, HTTPException, Request

from backend.app.admin_auth.dependencies import require_admin_permission
from backend.app.admin_auth.permissions import (
    PERMISSION_HUMAN_SUPPORT_READ,
    PERMISSION_HUMAN_SUPPORT_UPDATE,
)
from backend.app.api_utils.pilot_access import bind_citizen_request
from backend.app.durable_storage.models import (
    CitizenFeedbackRecord,
    EscalationRequestRecord,
)
from backend.app.human_support.models import (
    AdminQueueUpdateRequest,
    CitizenFeedbackCreateRequest,
    CitizenFeedbackResponse,
    EscalationCreateRequest,
    EscalationResponse,
    HumanSupportSummary,
)
from backend.app.human_support.service import HumanSupportService

router = APIRouter(tags=["human-support"])
_HUMAN_SUPPORT_SERVICE = HumanSupportService()


@router.post(
    "/api/human-support/feedback",
    response_model=CitizenFeedbackResponse,
)
def create_feedback(
    request: CitizenFeedbackCreateRequest,
    http_request: Request,
) -> CitizenFeedbackResponse:
    try:
        return _get_service(http_request).create_feedback(
            bind_citizen_request(http_request, request)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/api/human-support/escalations",
    response_model=EscalationResponse,
)
def create_escalation(
    request: EscalationCreateRequest,
    http_request: Request,
) -> EscalationResponse:
    try:
        return _get_service(http_request).create_escalation(
            bind_citizen_request(http_request, request)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/api/admin/human-support/feedback",
    response_model=list[CitizenFeedbackRecord],
    dependencies=[Depends(require_admin_permission(PERMISSION_HUMAN_SUPPORT_READ))],
)
def list_feedback(
    http_request: Request,
    status: str | None = None,
    limit: int = 50,
) -> list[CitizenFeedbackRecord]:
    return _get_service(http_request).list_feedback(status=status, limit=limit)


@router.patch(
    "/api/admin/human-support/feedback/{feedback_id}",
    response_model=CitizenFeedbackRecord,
    dependencies=[Depends(require_admin_permission(PERMISSION_HUMAN_SUPPORT_UPDATE))],
)
def update_feedback(
    feedback_id: str,
    request: AdminQueueUpdateRequest,
    http_request: Request,
) -> CitizenFeedbackRecord:
    try:
        return _get_service(http_request).update_feedback_status(feedback_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/api/admin/human-support/escalations",
    response_model=list[EscalationRequestRecord],
    dependencies=[Depends(require_admin_permission(PERMISSION_HUMAN_SUPPORT_READ))],
)
def list_escalations(
    http_request: Request,
    status: str | None = None,
    limit: int = 50,
) -> list[EscalationRequestRecord]:
    return _get_service(http_request).list_escalations(status=status, limit=limit)


@router.patch(
    "/api/admin/human-support/escalations/{escalation_id}",
    response_model=EscalationRequestRecord,
    dependencies=[Depends(require_admin_permission(PERMISSION_HUMAN_SUPPORT_UPDATE))],
)
def update_escalation(
    escalation_id: str,
    request: AdminQueueUpdateRequest,
    http_request: Request,
) -> EscalationRequestRecord:
    try:
        return _get_service(http_request).update_escalation_status(
            escalation_id,
            request,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/api/admin/human-support/summary",
    response_model=HumanSupportSummary,
    dependencies=[Depends(require_admin_permission(PERMISSION_HUMAN_SUPPORT_READ))],
)
def human_support_summary(http_request: Request) -> HumanSupportSummary:
    return _get_service(http_request).summarize()


def reset_human_support_demo_state_for_tests() -> None:
    _HUMAN_SUPPORT_SERVICE.reset_for_tests()


def _get_service(request: Request) -> HumanSupportService:
    service = getattr(request.app.state, "human_support_service", None)
    if isinstance(service, HumanSupportService):
        return service
    return _HUMAN_SUPPORT_SERVICE
