import threading
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from backend.app.admin_auth.dependencies import require_admin_permission
from backend.app.admin_auth.permissions import (
    PERMISSION_HUMAN_SUPPORT_READ,
    PERMISSION_HUMAN_SUPPORT_UPDATE,
    PERMISSION_SOURCE_CANDIDATES_REVIEW,
)
from backend.app.api.dependencies import get_source_registry
from backend.app.api_utils.identity_boundary import ResolvedIdentity, request_identity
from backend.app.config import get_settings
from backend.app.source_registry.registry import SourceRegistry
from backend.app.workspace.models import (
    CaseCreate,
    CasePatch,
    CaseStatus,
    ChecklistCreate,
    CommunityCreate,
    CommunityDecision,
    ConsulReply,
    ConsulStatus,
    ContextPatch,
    DocumentCreate,
    DocumentPatch,
    MessageCreate,
    OperatorReply,
    PlanCreate,
    ReplyCreate,
    StrictModel,
    SupportCreate,
    SupportPatch,
    TaskCreate,
    TaskPatch,
)
from backend.app.workspace.service import WorkspaceService
from backend.app.workspace.storage import WorkspaceRecoveryRequired

router = APIRouter(tags=["workspace"])
_INIT_LOCK = threading.Lock()
Limit = Annotated[int, Query(ge=1, le=50)]
Offset = Annotated[int, Query(ge=0, le=5000)]
Filter = Annotated[str | None, Query(max_length=100)]


def get_workspace_service(request: Request) -> WorkspaceService:
    with _INIT_LOCK:
        service = getattr(request.app.state, "workspace_service", None)
        if service is None:
            settings = getattr(request.app.state, "runtime_settings", None) or get_settings()
            try:
                service = WorkspaceService(
                    settings,
                    support=getattr(request.app.state, "human_support_service", None),
                )
            except WorkspaceRecoveryRequired as exc:
                raise HTTPException(503, "workspace_storage_recovery_required") from exc
            except OSError as exc:
                raise HTTPException(503, "workspace_storage_unavailable") from exc
            request.app.state.workspace_service = service
        if service.store and service.store.blocked:
            raise HTTPException(503, "workspace_storage_recovery_required")
        return service


def get_workspace_owner(request: Request) -> str:
    identity = request_identity(request)
    if identity is not None:
        return identity.owner
    service = get_workspace_service(request)
    settings = service.settings
    if (
        settings.PILOT_ACCESS_TOKENS.get_secret_value()
        or settings.QWEN_CHAT_ENABLED
        or settings.QWEN_OCR_ENABLED
    ):
        raise HTTPException(401, "pilot_access_required")
    headers = request.headers.getlist("x-workspace-session")
    if len(headers) != 1:
        raise HTTPException(401, "workspace_session_required")
    return service.demo_owner(headers[0])


Service = Annotated[WorkspaceService, Depends(get_workspace_service)]
Owner = Annotated[str, Depends(get_workspace_owner)]


def get_account(request: Request) -> dict:
    identity = request_identity(request)
    role = identity.account_type if identity else "citizen"
    return {"account_type": role, "local_preview": bool(identity and identity.local_preview),
            "identity_realm": identity.key.realm if identity else "demo",
            "capabilities": (["consul_requests", "consul_reply", "profile", "guide"]
                             if role == "consul" else
                             ["assistant", "personal_cases", "request_help", "profile", "guide"])}


def require_consul(request: Request) -> ResolvedIdentity:
    identity = request_identity(request)
    if identity is None or identity.account_type != "consul":
        raise HTTPException(403, "consul_account_required")
    return identity


Consul = Annotated[ResolvedIdentity, Depends(require_consul)]


@router.post("/api/workspace/session")
def workspace_session(request: Request, body: StrictModel, service: Service):
    identity = request_identity(request)
    pilot = identity is not None
    if not pilot and (
        service.settings.PILOT_ACCESS_TOKENS.get_secret_value()
        or service.settings.QWEN_CHAT_ENABLED
        or service.settings.QWEN_OCR_ENABLED
    ):
        raise HTTPException(401, "pilot_access_required")
    durable = pilot and service.store is not None
    return {
        "mode": "pilot" if pilot else "local_demo",
        "demo_session_token": None if pilot else service.issue_demo_session(),
        "persistent": durable,
        "persistence_mode": "durable" if durable else "local_session",
        "owner_scope": ("authenticated_external" if identity and identity.key.realm == "external"
                        else "authenticated_pilot" if pilot else "ephemeral_demo"),
        "not_production_identity": True,
        "session_lifetime_hours": None if pilot else 12,
        **get_account(request),
    }


@router.get("/api/workspace/profile")
def get_profile(request: Request, owner: Owner, service: Service):
    return {"profile": service.get_profile(owner), "account": get_account(request)}


@router.patch("/api/workspace/profile")
def patch_profile(body: ContextPatch, owner: Owner, service: Service):
    return {"profile": service.update_profile(owner, body)}


@router.delete("/api/workspace/profile")
def clear_profile(owner: Owner, service: Service):
    return {"profile": service.update_profile(owner, None)}


@router.get("/api/workspace/cases")
def list_cases(
    owner: Owner,
    service: Service,
    status: CaseStatus | None = None,
    limit: Limit = 30,
    offset: Offset = 0,
):
    return service.list_cases(owner, status, limit, offset)


@router.post("/api/workspace/cases")
def create_case(body: CaseCreate, owner: Owner, service: Service):
    return {"case": service.create_case(owner, body)}


@router.post("/api/workspace/plans")
def create_plan(body: PlanCreate, owner: Owner, service: Service):
    return {"case": service.create_plan(owner, body)}


@router.get("/api/workspace/cases/{case_id}")
def get_case(case_id: str, owner: Owner, service: Service):
    return {"case": service.get_case(owner, case_id)}


@router.patch("/api/workspace/cases/{case_id}")
def patch_case(case_id: str, body: CasePatch, owner: Owner, service: Service):
    return {"case": service.update_case(owner, case_id, body)}


@router.delete("/api/workspace/cases/{case_id}")
def delete_case(case_id: str, owner: Owner, service: Service):
    service.delete_case(owner, case_id)
    return {"deleted": True}


@router.post("/api/workspace/cases/{case_id}/tasks")
def add_task(case_id: str, body: TaskCreate, owner: Owner, service: Service):
    return {"case": service.add_task(owner, case_id, body)}


@router.patch("/api/workspace/cases/{case_id}/tasks/{task_id}")
def patch_task(case_id: str, task_id: str, body: TaskPatch, owner: Owner, service: Service):
    return {"case": service.update_task(owner, case_id, task_id, body)}


@router.post("/api/workspace/cases/{case_id}/checklist")
def generate_checklist(
    case_id: str, body: ChecklistCreate, owner: Owner, service: Service,
    registry: Annotated[SourceRegistry, Depends(get_source_registry)],
):
    return {"case": service.generate_checklist(owner, case_id, body, registry)}


@router.post("/api/workspace/cases/{case_id}/messages")
def add_message(case_id: str, body: MessageCreate, owner: Owner, service: Service):
    return {"case": service.add_message(owner, case_id, body)}


@router.post("/api/workspace/cases/{case_id}/documents")
def add_document(case_id: str, body: DocumentCreate, owner: Owner, service: Service):
    return {"case": service.add_document(owner, case_id, body)}


@router.patch("/api/workspace/cases/{case_id}/documents/{document_id}")
def patch_document(
    case_id: str, document_id: str, body: DocumentPatch, owner: Owner, service: Service
):
    return {"case": service.update_document(owner, case_id, document_id, body)}


@router.delete("/api/workspace/cases/{case_id}/documents/{document_id}")
def delete_document(case_id: str, document_id: str, owner: Owner, service: Service):
    return {"case": service.update_document(owner, case_id, document_id, None)}


@router.get("/api/workspace/support")
def list_tickets(owner: Owner, service: Service, limit: Limit = 30, offset: Offset = 0):
    return service.list_tickets(owner, limit, offset)


@router.post("/api/workspace/support")
def create_ticket(body: SupportCreate, owner: Owner, service: Service):
    return {"ticket": service.create_ticket(owner, body)}


@router.get("/api/workspace/support/{ticket_id}")
def get_ticket(ticket_id: str, owner: Owner, service: Service):
    return {"ticket": service.get_ticket(owner, ticket_id)}


@router.patch("/api/workspace/support/{ticket_id}")
def patch_ticket(ticket_id: str, body: SupportPatch, owner: Owner, service: Service):
    return {"ticket": service.update_ticket(owner, ticket_id, body.status)}


@router.post("/api/workspace/support/{ticket_id}/replies")
def reply_ticket(ticket_id: str, body: ReplyCreate, owner: Owner, service: Service):
    return {"ticket": service.reply_ticket(owner, ticket_id, body)}


@router.get("/api/consul/requests")
def consul_tickets(
    consul: Consul, service: Service, limit: Limit = 20, offset: Offset = 0,
    status: Annotated[str | None, Query(
        pattern="^(new|in_review|waiting_for_user|resolved|closed)$",
    )] = None,
):
    return service.consul_tickets(consul, status, limit, offset)


@router.get("/api/consul/requests/{ticket_id}")
def consul_ticket(ticket_id: str, consul: Consul, service: Service):
    return {"ticket": service.consul_ticket(consul, ticket_id)}


@router.post("/api/consul/requests/{ticket_id}/replies")
def consul_reply(ticket_id: str, body: ConsulReply, consul: Consul, service: Service):
    return {"ticket": service.consul_reply(consul, ticket_id, body)}


@router.patch("/api/consul/requests/{ticket_id}")
def consul_status(ticket_id: str, body: ConsulStatus, consul: Consul, service: Service):
    return {"ticket": service.consul_status(consul, ticket_id, body.status)}


@router.get(
    "/api/admin/workspace/support",
    dependencies=[
        Depends(require_admin_permission(PERMISSION_HUMAN_SUPPORT_READ)),
    ],
)
def operator_tickets(service: Service, limit: Limit = 30, offset: Offset = 0):
    return service.operator_tickets(limit, offset)


@router.post(
    "/api/admin/workspace/support/{ticket_id}/replies",
    dependencies=[
        Depends(require_admin_permission(PERMISSION_HUMAN_SUPPORT_UPDATE)),
    ],
)
def operator_reply(ticket_id: str, body: OperatorReply, service: Service):
    return {"ticket": service.operator_reply(ticket_id, body)}


@router.post("/api/workspace/community")
def create_post(body: CommunityCreate, owner: Owner, service: Service):
    return {"post": service.create_post(owner, body)}


@router.get("/api/workspace/community")
def list_posts(
    owner: Owner,
    service: Service,
    mine: bool = False,
    scenario: Filter = None,
    city: Filter = None,
    language: Filter = None,
    query: Filter = None,
    limit: Limit = 30,
    offset: Offset = 0,
):
    return service.list_posts(owner, mine, scenario, city, language, query, limit, offset)


@router.get("/api/workspace/library")
def library(
    owner: Owner,
    service: Service,
    registry: Annotated[SourceRegistry, Depends(get_source_registry)],
    scenario: Filter = None,
    city: Filter = None,
    query: Filter = None,
    include_demo: bool = False,
    limit: Limit = 30,
    offset: Offset = 0,
):
    return service.library(registry, scenario, city, query, include_demo, limit, offset)


@router.get(
    "/api/admin/workspace/community",
    dependencies=[
        Depends(require_admin_permission(PERMISSION_SOURCE_CANDIDATES_REVIEW)),
    ],
)
def operator_posts(service: Service, limit: Limit = 30, offset: Offset = 0):
    return service.operator_posts(limit, offset)


@router.patch(
    "/api/admin/workspace/community/{post_id}",
    dependencies=[
        Depends(require_admin_permission(PERMISSION_SOURCE_CANDIDATES_REVIEW)),
    ],
)
def decide_post(post_id: str, body: CommunityDecision, service: Service):
    return {"post": service.decide_post(post_id, body)}
