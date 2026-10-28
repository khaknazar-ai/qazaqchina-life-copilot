from typing import get_args

from pydantic import TypeAdapter

from backend.app.durable_storage.sqlite_store import SQLiteDurableStore
from backend.app.privacy.models import (
    DeleteRequestCreate,
    DeleteRequestRecord,
    DeleteRequestResponse,
    DeleteRequestStatus,
    DeleteRequestType,
    DeleteTargetScope,
    PrivacyControlsSummary,
    RedactionResult,
    utc_now,
)
from backend.app.privacy.pii import redact_pii, sanitize_metadata
from backend.app.privacy.retention import default_retention_policies
from backend.app.privacy.values import redact_private_value

DELETE_REQUEST_SAFETY_MESSAGE = (
    "Your request was recorded for review. This foundation does not perform verified legal "
    "deletion automatically."
)
OPEN_STATUSES = {"new", "in_review", "waiting_for_user", "verified"}
STATUS_TRANSITIONS: dict[str, set[str]] = {
    "new": {"in_review", "waiting_for_user", "rejected", "closed"},
    "in_review": {"waiting_for_user", "verified", "rejected", "closed"},
    "waiting_for_user": {"in_review", "rejected", "closed"},
    "verified": {"completed", "in_review", "closed"},
    "rejected": {"in_review", "closed"},
    "completed": {"closed"},
    "closed": set(),
}


class PrivacyService:
    def __init__(self, durable_store: SQLiteDurableStore | None = None) -> None:
        self.durable_store = durable_store
        self.delete_request_repository = None
        if durable_store is not None:
            from backend.app.durable_storage.repositories import (
                PrivacyDeleteRequestRepository,
            )

            self.delete_request_repository = PrivacyDeleteRequestRepository(durable_store)
        self._delete_requests: dict[str, DeleteRequestRecord] = {}

    def create_delete_request(
        self,
        request: DeleteRequestCreate,
    ) -> DeleteRequestResponse:
        message_redaction = redact_pii(request.message)
        contact_redaction = redact_pii(request.contact or "") if request.contact else None
        metadata = sanitize_metadata(
            {
                **request.metadata,
                "workflow_only": True,
                "legal_deletion_complete": False,
            }
        )
        record = DeleteRequestRecord(
            user_id=request.user_id,
            session_id=request.session_id,
            request_type=request.request_type,
            target_scope=request.target_scope,
            status="new",
            message_redacted=message_redaction.redacted_text,
            contact_redacted=contact_redaction.redacted_text if contact_redaction else None,
            metadata=metadata,
            pii_detected=(
                message_redaction.original_contains_pii
                or bool(contact_redaction and contact_redaction.original_contains_pii)
                or sanitize_metadata(request.metadata) != request.metadata
            ),
            notes=[
                "Delete request workflow record only.",
                "Verified legal deletion execution is not automatic in this foundation.",
            ],
        )
        self._store_delete_request(record)
        return DeleteRequestResponse(
            request_id=record.request_id,
            status=record.status,
            created_at=record.created_at,
            safety_message=DELETE_REQUEST_SAFETY_MESSAGE,
            stored=True,
            pii_redacted=record.pii_detected,
        )

    def list_delete_requests(
        self,
        status: DeleteRequestStatus | None = None,
        limit: int = 50,
    ) -> list[DeleteRequestRecord]:
        if status is not None:
            TypeAdapter(DeleteRequestStatus).validate_python(status)
        if self.delete_request_repository is not None:
            # Normalize legacy states before filtering so unknown states remain open.
            records = self.delete_request_repository.list(limit=max(limit, 10_000))
        else:
            records = list(self._delete_requests.values())
        records = [_safe_delete_request(record) for record in records]
        if status is not None:
            records = [record for record in records if record.status == status]
        return records[:limit]

    def update_delete_request_status(
        self,
        request_id: str,
        status: DeleteRequestStatus,
        note: str | None = None,
    ) -> DeleteRequestRecord:
        TypeAdapter(DeleteRequestStatus).validate_python(status)
        record = self._get_delete_request(request_id)
        if status != record.status and status not in STATUS_TRANSITIONS[record.status]:
            raise ValueError("Unsupported deletion request status transition.")
        notes = list(record.notes)
        if note:
            notes.append(redact_private_value(note))
        updated = record.model_copy(
            update={
                "status": status,
                "updated_at": utc_now(),
                "notes": notes,
            }
        )
        self._store_delete_request(updated)
        return updated

    def summarize(self) -> PrivacyControlsSummary:
        records = self.list_delete_requests(limit=10_000)
        policies = default_retention_policies()
        return PrivacyControlsSummary(
            delete_request_count=len(records),
            open_delete_request_count=sum(record.status in OPEN_STATUSES for record in records),
            retention_policy_count=len(policies),
            pii_redaction_available=True,
            raw_image_storage_allowed=False,
            legal_compliance_complete=False,
            used_network=False,
            used_external_provider=False,
            warnings=[
                "PII redaction is heuristic and not legal compliance certification.",
                "Delete requests are workflow records; verified deletion execution is future work.",
            ],
        )

    def redact_text(self, text: str) -> RedactionResult:
        return redact_pii(text)

    def sanitize_metadata(self, metadata: dict) -> dict:
        return sanitize_metadata(metadata)

    def reset_for_tests(self) -> None:
        self._delete_requests.clear()

    def _store_delete_request(self, record: DeleteRequestRecord) -> None:
        record = _safe_delete_request(record)
        if self.delete_request_repository is not None:
            self.delete_request_repository.add(record)
        else:
            self._delete_requests[record.request_id] = record

    def _get_delete_request(self, request_id: str) -> DeleteRequestRecord:
        if self.delete_request_repository is not None:
            record = self.delete_request_repository.get(request_id)
        else:
            record = self._delete_requests.get(request_id)
        if record is None:
            raise KeyError(f"Delete request not found: {request_id}")
        return _safe_delete_request(record)


def _safe_delete_request(record) -> DeleteRequestRecord:
    """Sanitize legacy reads without changing authoritative stored rows."""
    payload = record.model_dump(mode="python")
    notes = [redact_private_value(note) for note in payload.get("notes", [])]
    if payload.get("request_type") not in get_args(DeleteRequestType):
        payload["request_type"] = "delete_my_data"
        notes.append("Legacy request type normalized for privacy review.")
    if payload.get("status") not in get_args(DeleteRequestStatus):
        payload["status"] = "new"
        notes.append("Legacy unknown status requires operator review.")
    if payload.get("target_scope") not in get_args(DeleteTargetScope):
        payload["target_scope"] = "all_known_data"
    metadata = sanitize_metadata(payload.get("metadata", {}))
    message = redact_pii(payload["message_redacted"]).redacted_text
    contact = (
        redact_pii(payload["contact_redacted"]).redacted_text
        if payload.get("contact_redacted") else None
    )
    changed = (
        metadata != payload.get("metadata", {}) or notes != payload.get("notes", [])
        or message != payload["message_redacted"] or contact != payload.get("contact_redacted")
    )
    payload.update(
        metadata=metadata, notes=notes, message_redacted=message, contact_redacted=contact,
        pii_detected=payload.get("pii_detected", False) or changed,
    )
    return DeleteRequestRecord.model_validate(payload)
