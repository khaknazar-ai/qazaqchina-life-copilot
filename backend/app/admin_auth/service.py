import hmac

from backend.app.admin_auth.models import (
    AdminAuthConfig,
    AdminAuthDecision,
    AdminTokenConfig,
    AuthenticatedAdmin,
)
from backend.app.admin_auth.permissions import (
    ROLE_PERMISSIONS,
    ROLE_SUPER_ADMIN,
    all_permissions,
    permissions_for_roles,
)
from backend.app.config import Settings
from backend.app.durable_storage.models import AdminAuditEvent


def validate_runtime_settings(settings: Settings) -> None:
    if settings.APP_ENV.casefold() not in {"development", "local", "demo", "test"}:
        raise ValueError(
            "This backend is local/internal-demo only. Production/staging startup is "
            "blocked until citizen identity, ownership controls and deployment are ready."
        )
    if settings.ADMIN_AUTH_ENABLED:
        token = settings.ADMIN_AUTH_TOKEN.get_secret_value()
        roles = [role.strip() for role in settings.ADMIN_AUTH_ROLES.split(",") if role.strip()]
        if len(token) < 32 or not token.isascii() or any(char.isspace() for char in token):
            raise ValueError(
                "Enabled admin auth requires a nonblank ASCII token of 32+ characters."
            )
        if not roles or any(role not in ROLE_PERMISSIONS for role in roles):
            raise ValueError("ADMIN_AUTH_ROLES must contain supported administrator roles.")
        review_token = settings.ADMIN_REVIEW_AUTH_TOKEN.get_secret_value()
        if review_token:
            review_roles = [
                role.strip() for role in settings.ADMIN_REVIEW_AUTH_ROLES.split(",") if role.strip()
            ]
            if len(review_token) < 32 or not review_token.isascii() or (
                any(char.isspace() for char in review_token)
            ):
                raise ValueError(
                    "The second review token must be nonblank ASCII with 32+ characters."
                )
            if not review_roles or any(role not in ROLE_PERMISSIONS for role in review_roles):
                raise ValueError("ADMIN_REVIEW_AUTH_ROLES must contain supported review roles.")
            if hmac.compare_digest(token, review_token):
                raise ValueError("Review accounts must use different tokens.")
            primary_actor = settings.ADMIN_AUTH_ACTOR_ID.strip()
            review_actor = settings.ADMIN_REVIEW_AUTH_ACTOR_ID.strip()
            if not primary_actor or not review_actor or primary_actor == review_actor:
                raise ValueError("Review accounts must have distinct nonblank actor identifiers.")
            if primary_actor != settings.ADMIN_AUTH_ACTOR_ID or (
                review_actor != settings.ADMIN_REVIEW_AUTH_ACTOR_ID
            ):
                raise ValueError("Review actor identifiers cannot have surrounding whitespace.")


def build_admin_auth_service(settings: Settings) -> "AdminAuthService":
    validate_runtime_settings(settings)
    tokens = []
    if settings.ADMIN_AUTH_ENABLED:
        tokens = [
            AdminTokenConfig(
                token_id="environment-admin-token",
                token_value=settings.ADMIN_AUTH_TOKEN.get_secret_value(),
                actor_id=settings.ADMIN_AUTH_ACTOR_ID,
                roles=[
                    role.strip() for role in settings.ADMIN_AUTH_ROLES.split(",") if role.strip()
                ],
            )
        ]
        review_token = settings.ADMIN_REVIEW_AUTH_TOKEN.get_secret_value()
        if review_token:
            tokens.append(AdminTokenConfig(
                token_id="environment-review-token",
                token_value=review_token,
                actor_id=settings.ADMIN_REVIEW_AUTH_ACTOR_ID,
                roles=[
                    role.strip() for role in settings.ADMIN_REVIEW_AUTH_ROLES.split(",")
                    if role.strip()
                ],
            ))
    return AdminAuthService(AdminAuthConfig(enabled=settings.ADMIN_AUTH_ENABLED, tokens=tokens))


class AdminAuthService:
    def __init__(self, config: AdminAuthConfig | None = None) -> None:
        self.config = config or AdminAuthConfig()

    def is_enabled(self) -> bool:
        return self.config.enabled

    def authenticate_bearer_token(self, token: str | None) -> AdminAuthDecision:
        if not self.config.enabled:
            actor = AuthenticatedAdmin(
                actor_id="local-dev-admin",
                token_id=None,
                roles=[ROLE_SUPER_ADMIN],
                permissions=sorted(all_permissions()),
                auth_mode=self.config.mode,
            )
            return AdminAuthDecision(
                authenticated=True,
                actor=actor,
                reason="auth_disabled_local_dev",
                warnings=["admin auth disabled; local/dev only"],
            )

        normalized_token = (token or "").strip()
        if normalized_token and not normalized_token.isascii():
            return AdminAuthDecision(authenticated=False, reason="invalid_bearer_token")
        if not normalized_token:
            return AdminAuthDecision(
                authenticated=False,
                reason="missing_bearer_token",
                warnings=["Admin auth is enabled; bearer token is required."],
            )

        for configured_token in self.config.tokens:
            if not hmac.compare_digest(normalized_token, configured_token.token_value):
                continue
            if not configured_token.active:
                return AdminAuthDecision(
                    authenticated=False,
                    reason="inactive_token",
                    warnings=["Admin token is inactive."],
                )
            permissions = sorted(permissions_for_roles(configured_token.roles))
            actor = AuthenticatedAdmin(
                actor_id=configured_token.actor_id,
                token_id=configured_token.token_id,
                roles=list(configured_token.roles),
                permissions=permissions,
                auth_mode=self.config.mode,
            )
            return AdminAuthDecision(authenticated=True, actor=actor)

        return AdminAuthDecision(
            authenticated=False,
            reason="invalid_bearer_token",
            warnings=["Admin bearer token was not accepted."],
        )

    def require_permission(
        self,
        token: str | None,
        permission: str,
    ) -> AdminAuthDecision:
        decision = self.authenticate_bearer_token(token)
        if not decision.authenticated:
            return decision.model_copy(update={"required_permission": permission})
        actor_permissions = set(decision.actor.permissions if decision.actor else [])
        if permission not in actor_permissions:
            return AdminAuthDecision(
                authenticated=False,
                actor=decision.actor,
                reason="permission_denied",
                required_permission=permission,
                warnings=[f"Admin permission required: {permission}."],
            )
        return decision.model_copy(update={"required_permission": permission})

    def build_audit_event(
        self,
        decision: AdminAuthDecision,
        event_type: str = "admin_auth_check",
        target_type: str | None = "admin_auth",
        target_id: str | None = None,
    ) -> AdminAuditEvent:
        actor = decision.actor
        return AdminAuditEvent(
            event_type=event_type,
            actor_id=actor.actor_id if actor else None,
            target_type=target_type,
            target_id=target_id,
            reason=decision.reason,
            metadata={
                "authenticated": decision.authenticated,
                "required_permission": decision.required_permission,
                "roles": actor.roles if actor else [],
                "token_id": actor.token_id if actor else None,
            },
        )
