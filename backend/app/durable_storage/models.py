from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

RAW_IMAGE_METADATA_KEYS = {
    "image_base64",
    "raw_image",
    "image_bytes",
    "file_bytes",
    "base64",
    "data_url",
}


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_utc(value: datetime | str | None = None) -> str:
    if value is None:
        return utc_now().isoformat()
    if isinstance(value, datetime):
        active = value if value.tzinfo else value.replace(tzinfo=UTC)
        return active.astimezone(UTC).isoformat()
    return value


def sanitize_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not metadata:
        return {}
    _reject_raw_image_metadata(metadata)
    return dict(metadata)


def reject_raw_image_metadata(metadata: dict[str, Any] | None) -> None:
    if metadata:
        _reject_raw_image_metadata(metadata)


class DurableStorageConfig(BaseModel):
    db_path: str
    auto_initialize: bool = True


class _MetadataModel(BaseModel):
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata", mode="before")
    @classmethod
    def _validate_metadata(cls, value):
        return sanitize_metadata(value)


class AdminAuditEvent(_MetadataModel):
    event_id: str = Field(default_factory=lambda: f"admin-audit-{uuid4().hex}")
    event_type: str
    actor_id: str | None = None
    target_type: str | None = None
    target_id: str | None = None
    reason: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class CitizenFeedbackRecord(_MetadataModel):
    feedback_id: str = Field(default_factory=lambda: f"feedback-{uuid4().hex}")
    user_id: str | None = None
    session_id: str | None = None
    category: str | None = None
    message: str
    severity: str | None = None
    status: str | None = "open"
    created_at: datetime = Field(default_factory=utc_now)


class EscalationRequestRecord(_MetadataModel):
    escalation_id: str = Field(default_factory=lambda: f"escalation-{uuid4().hex}")
    user_id: str | None = None
    session_id: str | None = None
    scenario: str | None = None
    risk_level: str | None = None
    summary: str
    status: str | None = "open"
    assigned_to: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class SourceReviewAuditRecord(_MetadataModel):
    review_event_id: str = Field(default_factory=lambda: f"source-review-{uuid4().hex}")
    source_id: str | None = None
    candidate_id: str | None = None
    version_id: str | None = None
    reviewer_id: str | None = None
    decision: str
    reason: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class ConversationTurnRecord(_MetadataModel):
    turn_id: str = Field(default_factory=lambda: f"turn-{uuid4().hex}")
    user_id: str | None = None
    session_id: str | None = None
    role: str
    text: str
    scenario: str | None = None
    risk_level: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class PhotoIntakeMetadataRecord(_MetadataModel):
    photo_event_id: str = Field(default_factory=lambda: f"photo-event-{uuid4().hex}")
    user_id: str | None = None
    session_id: str | None = None
    image_hash: str | None = None
    detected_type: str | None = None
    size_bytes: int | None = None
    manual_transcription_used: bool = False
    not_trusted_evidence: bool = True
    created_at: datetime = Field(default_factory=utc_now)


class PrivacyDeleteRequestRecord(_MetadataModel):
    request_id: str = Field(default_factory=lambda: f"delete-request-{uuid4().hex}")
    user_id: str | None = None
    session_id: str | None = None
    request_type: str
    target_scope: str | None = None
    status: str | None = "new"
    message_redacted: str
    contact_redacted: str | None = None
    pii_detected: bool = False
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    notes: list[str] = Field(default_factory=list)


class DurableStorageHealthReport(BaseModel):
    db_path: str
    initialized: bool
    table_count: int
    expected_tables_present: bool
    record_counts: dict[str, int] = Field(default_factory=dict)
    raw_image_storage_allowed: bool = False
    production_database: bool = False
    used_network: bool = False
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


def _reject_raw_image_metadata(value: Any, path: str = "metadata") -> None:
    if isinstance(value, dict):
        for key, nested_value in value.items():
            normalized = str(key).casefold()
            if normalized in RAW_IMAGE_METADATA_KEYS:
                raise ValueError(f"Raw image metadata key is not allowed: {path}.{key}")
            _reject_raw_image_metadata(nested_value, f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested_value in enumerate(value):
            _reject_raw_image_metadata(nested_value, f"{path}[{index}]")
