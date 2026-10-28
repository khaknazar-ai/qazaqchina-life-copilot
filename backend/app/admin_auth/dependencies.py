from collections.abc import Callable

from fastapi import Header, HTTPException, Request

from backend.app.admin_auth.models import AdminAuthDecision
from backend.app.admin_auth.service import AdminAuthService, build_admin_auth_service
from backend.app.config import get_settings
from backend.app.durable_storage.repositories import AdminAuditRepository


def get_bearer_token_from_authorization_header(header: str | None) -> str | None:
    if not header:
        return None
    scheme, _, value = header.partition(" ")
    if scheme.casefold() != "bearer" or not value.strip():
        return None
    return value.strip()


def get_admin_auth_service(request: Request) -> AdminAuthService:
    service = getattr(request.app.state, "admin_auth_service", None)
    if isinstance(service, AdminAuthService):
        return service
    settings = getattr(request.app.state, "runtime_settings", None) or get_settings()
    return build_admin_auth_service(settings)


def require_admin_permission(permission: str) -> Callable:
    def dependency(
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> AdminAuthDecision:
        service = get_admin_auth_service(request)
        token = get_bearer_token_from_authorization_header(authorization)
        decision = service.require_permission(token, permission)
        store = getattr(request.app.state, "durable_store", None)
        if store is not None and service.config.audit_enabled:
            AdminAuditRepository(store).add(
                service.build_audit_event(
                    decision,
                    event_type="admin_permission_check",
                    target_type="api_route",
                    target_id=getattr(request.scope.get("route"), "path", None),
                )
            )
        if not decision.authenticated:
            status_code = 403
            if decision.reason in {
                "missing_bearer_token",
                "invalid_bearer_token",
                "inactive_token",
            }:
                status_code = 401
            raise HTTPException(
                status_code=status_code,
                detail={
                    "reason": decision.reason,
                    "required_permission": decision.required_permission,
                    "warnings": decision.warnings,
                },
            )
        return decision

    return dependency
