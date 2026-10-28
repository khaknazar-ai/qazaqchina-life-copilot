from datetime import UTC, datetime

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


class AdminTokenConfig(BaseModel):
    token_id: str
    token_value: str = Field(repr=False, exclude=True)
    actor_id: str
    roles: list[str] = Field(default_factory=list)
    active: bool = True


class AdminAuthConfig(BaseModel):
    enabled: bool = False
    mode: str = "local_token"
    tokens: list[AdminTokenConfig] = Field(default_factory=list)
    audit_enabled: bool = True


class AuthenticatedAdmin(BaseModel):
    actor_id: str
    token_id: str | None = None
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    auth_mode: str = "local_token"


class AdminAuthDecision(BaseModel):
    authenticated: bool
    actor: AuthenticatedAdmin | None = None
    reason: str | None = None
    required_permission: str | None = None
    warnings: list[str] = Field(default_factory=list)


class AdminAuthReadinessReport(BaseModel):
    generated_at: datetime = Field(default_factory=utc_now)
    enabled: bool
    mode: str
    configured_token_count: int
    production_ready: bool = False
    hardcoded_secret_detected: bool = False
    default_open_mode: bool
    roles_defined: list[str] = Field(default_factory=list)
    permissions_defined: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    used_network: bool = False
    used_external_provider: bool = False
