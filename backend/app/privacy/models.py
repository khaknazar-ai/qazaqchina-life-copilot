from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

DeleteTargetScope = Literal[
    "session",
    "user",
    "feedback",
    "escalation",
    "photo_metadata",
    "all_known_data",
]
DeleteRequestStatus = Literal[
    "new",
    "in_review",
    "waiting_for_user",
    "verified",
    "rejected",
    "completed",
    "closed",
]
DeleteRequestType = Literal["delete_my_data"]


def utc_now() -> datetime:
    return datetime.now(UTC)


class PIIDetection(BaseModel):
    category: str
    matched: str | None = None
    start: int | None = None
    end: int | None = None
    confidence: str = "heuristic"
    warning: str | None = None


class RedactionResult(BaseModel):
    original_contains_pii: bool
    redacted_text: str
    detections: list[PIIDetection] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RetentionPolicy(BaseModel):
    category: str
    default_retention_days: int
    description: str
    delete_on_request: bool = True
    requires_admin_review: bool = False


class DeleteRequestCreate(BaseModel):
    user_id: str | None = None
    session_id: str | None = None
    request_type: DeleteRequestType = "delete_my_data"
    message: str
    contact: str | None = None
    target_scope: DeleteTargetScope = "session"
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeleteRequestRecord(BaseModel):
    request_id: str = Field(default_factory=lambda: f"delete-request-{uuid4().hex}")
    user_id: str | None = None
    session_id: str | None = None
    request_type: DeleteRequestType
    target_scope: DeleteTargetScope
    status: DeleteRequestStatus = "new"
    message_redacted: str
    contact_redacted: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    pii_detected: bool = False
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    notes: list[str] = Field(default_factory=list)


class DeleteRequestResponse(BaseModel):
    request_id: str
    status: DeleteRequestStatus
    created_at: datetime
    safety_message: str
    stored: bool
    pii_redacted: bool


class PrivacyControlsSummary(BaseModel):
    delete_request_count: int
    open_delete_request_count: int
    retention_policy_count: int
    pii_redaction_available: bool
    raw_image_storage_allowed: bool = False
    legal_compliance_complete: bool = False
    used_network: bool = False
    used_external_provider: bool = False
    warnings: list[str] = Field(default_factory=list)
