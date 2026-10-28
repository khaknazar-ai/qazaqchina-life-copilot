import json
from typing import Any

from backend.app.durable_storage.models import (
    AdminAuditEvent,
    CitizenFeedbackRecord,
    ConversationTurnRecord,
    EscalationRequestRecord,
    PhotoIntakeMetadataRecord,
    PrivacyDeleteRequestRecord,
    SourceReviewAuditRecord,
    iso_utc,
    sanitize_metadata,
    utc_now,
)
from backend.app.durable_storage.sqlite_store import SQLiteDurableStore


class AdminAuditRepository:
    def __init__(self, store: SQLiteDurableStore) -> None:
        self.store = store

    def add(self, event: AdminAuditEvent) -> AdminAuditEvent:
        metadata = _metadata_json(event.metadata)
        self.store.execute(
            """
            INSERT OR REPLACE INTO admin_audit_events (
                event_id, event_type, actor_id, target_type, target_id, reason,
                metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                event.event_type,
                event.actor_id,
                event.target_type,
                event.target_id,
                event.reason,
                metadata,
                iso_utc(event.created_at),
            ),
        )
        return event

    def list(self, limit: int = 50) -> list[AdminAuditEvent]:
        rows = self.store.query(
            """
            SELECT * FROM admin_audit_events
            ORDER BY created_at ASC, event_id ASC
            LIMIT ?
            """,
            (limit,),
        )
        return [_admin_audit_from_row(row) for row in rows]


class CitizenFeedbackRepository:
    def __init__(self, store: SQLiteDurableStore) -> None:
        self.store = store

    def add(self, record: CitizenFeedbackRecord) -> CitizenFeedbackRecord:
        self.store.execute(
            """
            INSERT OR REPLACE INTO citizen_feedback (
                feedback_id, user_id, session_id, category, message, severity, status,
                metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.feedback_id,
                record.user_id,
                record.session_id,
                record.category,
                record.message,
                record.severity,
                record.status,
                _metadata_json(record.metadata),
                iso_utc(record.created_at),
            ),
        )
        return record

    def list(
        self,
        status: str | None = None,
        limit: int = 50,
    ) -> list[CitizenFeedbackRecord]:
        if status is None:
            rows = self.store.query(
                """
                SELECT * FROM citizen_feedback
                ORDER BY created_at ASC, feedback_id ASC
                LIMIT ?
                """,
                (limit,),
            )
        else:
            rows = self.store.query(
                """
                SELECT * FROM citizen_feedback
                WHERE status = ?
                ORDER BY created_at ASC, feedback_id ASC
                LIMIT ?
                """,
                (status, limit),
            )
        return [_feedback_from_row(row) for row in rows]

    def get(self, feedback_id: str) -> CitizenFeedbackRecord | None:
        rows = self.store.query(
            "SELECT * FROM citizen_feedback WHERE feedback_id = ?",
            (feedback_id,),
        )
        return _feedback_from_row(rows[0]) if rows else None

    def update_status(
        self,
        feedback_id: str,
        status: str,
    ) -> CitizenFeedbackRecord | None:
        self.store.execute(
            "UPDATE citizen_feedback SET status = ? WHERE feedback_id = ?",
            (status, feedback_id),
        )
        return self.get(feedback_id)


class EscalationRepository:
    def __init__(self, store: SQLiteDurableStore) -> None:
        self.store = store

    def add(self, record: EscalationRequestRecord) -> EscalationRequestRecord:
        self.store.execute(
            """
            INSERT OR REPLACE INTO escalation_requests (
                escalation_id, user_id, session_id, scenario, risk_level, summary, status,
                assigned_to, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.escalation_id,
                record.user_id,
                record.session_id,
                record.scenario,
                record.risk_level,
                record.summary,
                record.status,
                record.assigned_to,
                _metadata_json(record.metadata),
                iso_utc(record.created_at),
                iso_utc(record.updated_at),
            ),
        )
        return record

    def list(
        self,
        status: str | None = None,
        limit: int = 50,
    ) -> list[EscalationRequestRecord]:
        if status is None:
            rows = self.store.query(
                """
                SELECT * FROM escalation_requests
                ORDER BY created_at ASC, escalation_id ASC
                LIMIT ?
                """,
                (limit,),
            )
        else:
            rows = self.store.query(
                """
                SELECT * FROM escalation_requests
                WHERE status = ?
                ORDER BY created_at ASC, escalation_id ASC
                LIMIT ?
                """,
                (status, limit),
            )
        return [_escalation_from_row(row) for row in rows]

    def get(self, escalation_id: str) -> EscalationRequestRecord | None:
        rows = self.store.query(
            "SELECT * FROM escalation_requests WHERE escalation_id = ?",
            (escalation_id,),
        )
        return _escalation_from_row(rows[0]) if rows else None

    def find_workspace_ticket(
        self, owner: str, ticket_id: str
    ) -> EscalationRequestRecord | None:
        rows = self.store.query(
            """
            SELECT * FROM escalation_requests
            WHERE user_id = ?
              AND json_extract(metadata_json, '$.workspace_ticket_id') = ?
            ORDER BY created_at ASC, escalation_id ASC
            LIMIT 1
            """,
            (owner, ticket_id),
        )
        return _escalation_from_row(rows[0]) if rows else None

    def update_status(
        self,
        escalation_id: str,
        status: str,
        assigned_to: str | None = None,
    ) -> EscalationRequestRecord | None:
        existing = self.get(escalation_id)
        if existing is None:
            return None
        self.store.execute(
            """
            UPDATE escalation_requests
            SET status = ?, assigned_to = ?, updated_at = ?
            WHERE escalation_id = ?
            """,
            (status, assigned_to or existing.assigned_to, iso_utc(utc_now()), escalation_id),
        )
        return self.get(escalation_id)


class SourceReviewAuditRepository:
    def __init__(self, store: SQLiteDurableStore) -> None:
        self.store = store

    def add(self, record: SourceReviewAuditRecord) -> SourceReviewAuditRecord:
        self.store.execute(
            """
            INSERT OR REPLACE INTO source_review_audit (
                review_event_id, source_id, candidate_id, version_id, reviewer_id, decision,
                reason, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.review_event_id,
                record.source_id,
                record.candidate_id,
                record.version_id,
                record.reviewer_id,
                record.decision,
                record.reason,
                _metadata_json(record.metadata),
                iso_utc(record.created_at),
            ),
        )
        return record

    def list(
        self,
        source_id: str | None = None,
        candidate_id: str | None = None,
        limit: int = 50,
    ) -> list[SourceReviewAuditRecord]:
        clauses: list[str] = []
        parameters: list[Any] = []
        if source_id is not None:
            clauses.append("source_id = ?")
            parameters.append(source_id)
        if candidate_id is not None:
            clauses.append("candidate_id = ?")
            parameters.append(candidate_id)
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        parameters.append(limit)
        rows = self.store.query(
            f"""
            SELECT * FROM source_review_audit
            {where_clause}
            ORDER BY created_at ASC, review_event_id ASC
            LIMIT ?
            """,
            tuple(parameters),
        )
        return [_source_review_from_row(row) for row in rows]


class ConversationTurnRepository:
    def __init__(self, store: SQLiteDurableStore) -> None:
        self.store = store

    def add(self, record: ConversationTurnRecord) -> ConversationTurnRecord:
        self.store.execute(
            """
            INSERT OR REPLACE INTO conversation_turns (
                turn_id, user_id, session_id, role, text, scenario, risk_level,
                metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.turn_id,
                record.user_id,
                record.session_id,
                record.role,
                record.text,
                record.scenario,
                record.risk_level,
                _metadata_json(record.metadata),
                iso_utc(record.created_at),
            ),
        )
        return record

    def list_by_session(
        self,
        session_id: str,
        limit: int = 50,
    ) -> list[ConversationTurnRecord]:
        rows = self.store.query(
            """
            SELECT * FROM conversation_turns
            WHERE session_id = ?
            ORDER BY created_at ASC, turn_id ASC
            LIMIT ?
            """,
            (session_id, limit),
        )
        return [_conversation_from_row(row) for row in rows]


class PhotoIntakeMetadataRepository:
    def __init__(self, store: SQLiteDurableStore) -> None:
        self.store = store

    def add(self, record: PhotoIntakeMetadataRecord) -> PhotoIntakeMetadataRecord:
        self.store.execute(
            """
            INSERT OR REPLACE INTO photo_intake_metadata (
                photo_event_id, user_id, session_id, image_hash, detected_type, size_bytes,
                manual_transcription_used, not_trusted_evidence, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.photo_event_id,
                record.user_id,
                record.session_id,
                record.image_hash,
                record.detected_type,
                record.size_bytes,
                int(record.manual_transcription_used),
                int(record.not_trusted_evidence),
                _metadata_json(record.metadata),
                iso_utc(record.created_at),
            ),
        )
        return record

    def list_by_session(
        self,
        session_id: str,
        limit: int = 50,
    ) -> list[PhotoIntakeMetadataRecord]:
        rows = self.store.query(
            """
            SELECT * FROM photo_intake_metadata
            WHERE session_id = ?
            ORDER BY created_at ASC, photo_event_id ASC
            LIMIT ?
            """,
            (session_id, limit),
        )
        return [_photo_metadata_from_row(row) for row in rows]


class PrivacyDeleteRequestRepository:
    def __init__(self, store: SQLiteDurableStore) -> None:
        self.store = store

    def add(self, record: PrivacyDeleteRequestRecord) -> PrivacyDeleteRequestRecord:
        metadata = dict(record.metadata)
        if record.notes:
            metadata["notes"] = list(record.notes)
        self.store.execute(
            """
            INSERT OR REPLACE INTO privacy_delete_requests (
                request_id, user_id, session_id, request_type, target_scope, status,
                message_redacted, contact_redacted, metadata_json, pii_detected,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.request_id,
                record.user_id,
                record.session_id,
                record.request_type,
                record.target_scope,
                record.status,
                record.message_redacted,
                record.contact_redacted,
                _metadata_json(metadata),
                int(record.pii_detected),
                iso_utc(record.created_at),
                iso_utc(record.updated_at),
            ),
        )
        return record

    def list(
        self,
        status: str | None = None,
        limit: int = 50,
    ) -> list[PrivacyDeleteRequestRecord]:
        if status is None:
            rows = self.store.query(
                """
                SELECT * FROM privacy_delete_requests
                ORDER BY created_at ASC, request_id ASC
                LIMIT ?
                """,
                (limit,),
            )
        else:
            rows = self.store.query(
                """
                SELECT * FROM privacy_delete_requests
                WHERE status = ?
                ORDER BY created_at ASC, request_id ASC
                LIMIT ?
                """,
                (status, limit),
            )
        return [_privacy_delete_request_from_row(row) for row in rows]

    def get(self, request_id: str) -> PrivacyDeleteRequestRecord | None:
        rows = self.store.query(
            "SELECT * FROM privacy_delete_requests WHERE request_id = ?",
            (request_id,),
        )
        return _privacy_delete_request_from_row(rows[0]) if rows else None

    def update_status(
        self,
        request_id: str,
        status: str,
        note: str | None = None,
    ) -> PrivacyDeleteRequestRecord | None:
        existing = self.get(request_id)
        if existing is None:
            return None
        notes = list(existing.notes)
        if note:
            notes.append(note)
        metadata = dict(existing.metadata)
        metadata["notes"] = notes
        self.store.execute(
            """
            UPDATE privacy_delete_requests
            SET status = ?, metadata_json = ?, updated_at = ?
            WHERE request_id = ?
            """,
            (status, _metadata_json(metadata), iso_utc(utc_now()), request_id),
        )
        return self.get(request_id)


def _metadata_json(metadata: dict[str, Any]) -> str:
    return json.dumps(sanitize_metadata(metadata), ensure_ascii=False, sort_keys=True)


def _metadata(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    parsed = json.loads(value)
    return parsed if isinstance(parsed, dict) else {}


def _admin_audit_from_row(row: dict[str, Any]) -> AdminAuditEvent:
    return AdminAuditEvent(
        event_id=row["event_id"],
        event_type=row["event_type"],
        actor_id=row["actor_id"],
        target_type=row["target_type"],
        target_id=row["target_id"],
        reason=row["reason"],
        metadata=_metadata(row["metadata_json"]),
        created_at=row["created_at"],
    )


def _feedback_from_row(row: dict[str, Any]) -> CitizenFeedbackRecord:
    return CitizenFeedbackRecord(
        feedback_id=row["feedback_id"],
        user_id=row["user_id"],
        session_id=row["session_id"],
        category=row["category"],
        message=row["message"],
        severity=row["severity"],
        status=row["status"],
        metadata=_metadata(row["metadata_json"]),
        created_at=row["created_at"],
    )


def _escalation_from_row(row: dict[str, Any]) -> EscalationRequestRecord:
    return EscalationRequestRecord(
        escalation_id=row["escalation_id"],
        user_id=row["user_id"],
        session_id=row["session_id"],
        scenario=row["scenario"],
        risk_level=row["risk_level"],
        summary=row["summary"],
        status=row["status"],
        assigned_to=row["assigned_to"],
        metadata=_metadata(row["metadata_json"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _source_review_from_row(row: dict[str, Any]) -> SourceReviewAuditRecord:
    return SourceReviewAuditRecord(
        review_event_id=row["review_event_id"],
        source_id=row["source_id"],
        candidate_id=row["candidate_id"],
        version_id=row["version_id"],
        reviewer_id=row["reviewer_id"],
        decision=row["decision"],
        reason=row["reason"],
        metadata=_metadata(row["metadata_json"]),
        created_at=row["created_at"],
    )


def _conversation_from_row(row: dict[str, Any]) -> ConversationTurnRecord:
    return ConversationTurnRecord(
        turn_id=row["turn_id"],
        user_id=row["user_id"],
        session_id=row["session_id"],
        role=row["role"],
        text=row["text"],
        scenario=row["scenario"],
        risk_level=row["risk_level"],
        metadata=_metadata(row["metadata_json"]),
        created_at=row["created_at"],
    )


def _photo_metadata_from_row(row: dict[str, Any]) -> PhotoIntakeMetadataRecord:
    return PhotoIntakeMetadataRecord(
        photo_event_id=row["photo_event_id"],
        user_id=row["user_id"],
        session_id=row["session_id"],
        image_hash=row["image_hash"],
        detected_type=row["detected_type"],
        size_bytes=row["size_bytes"],
        manual_transcription_used=bool(row["manual_transcription_used"]),
        not_trusted_evidence=bool(row["not_trusted_evidence"]),
        metadata=_metadata(row["metadata_json"]),
        created_at=row["created_at"],
    )


def _privacy_delete_request_from_row(row: dict[str, Any]) -> PrivacyDeleteRequestRecord:
    metadata = _metadata(row["metadata_json"])
    notes = metadata.pop("notes", [])
    return PrivacyDeleteRequestRecord(
        request_id=row["request_id"],
        user_id=row["user_id"],
        session_id=row["session_id"],
        request_type=row["request_type"],
        target_scope=row["target_scope"],
        status=row["status"],
        message_redacted=row["message_redacted"],
        contact_redacted=row["contact_redacted"],
        metadata=metadata,
        pii_detected=bool(row["pii_detected"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        notes=notes if isinstance(notes, list) else [],
    )
