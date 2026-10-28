import re

from backend.app.durable_storage.models import (
    CitizenFeedbackRecord,
    EscalationRequestRecord,
    sanitize_metadata,
    utc_now,
)
from backend.app.durable_storage.repositories import (
    CitizenFeedbackRepository,
    EscalationRepository,
)
from backend.app.durable_storage.sqlite_store import SQLiteDurableStore
from backend.app.human_support.models import (
    AdminQueueUpdateRequest,
    CitizenFeedbackCreateRequest,
    CitizenFeedbackResponse,
    EscalationCreateRequest,
    EscalationResponse,
    HumanSupportSummary,
)
from backend.app.privacy.values import redact_private_value

NOT_EMERGENCY_DISPATCH_MESSAGE = (
    "This queue is not emergency dispatch. Contact local emergency services/official "
    "authorities if immediate danger exists."
)
FEEDBACK_SAFETY_MESSAGE = (
    "Feedback was recorded for review. Feedback text is user-provided input and is not "
    "trusted source evidence."
)
OPEN_STATUSES = {"new", "in_review", "waiting_for_user", "escalated", "open"}
_TRACE_UUID = re.compile(r"[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}")


def _related_turn(value: str | None) -> str | None:
    return value if value and _TRACE_UUID.fullmatch(value) else redact_private_value(value)


class HumanSupportService:
    def __init__(self, durable_store: SQLiteDurableStore | None = None) -> None:
        self.durable_store = durable_store
        self.feedback_repository = (
            CitizenFeedbackRepository(durable_store) if durable_store is not None else None
        )
        self.escalation_repository = (
            EscalationRepository(durable_store) if durable_store is not None else None
        )
        self._feedback_records: dict[str, CitizenFeedbackRecord] = {}
        self._escalation_records: dict[str, EscalationRequestRecord] = {}

    def create_feedback(
        self,
        request: CitizenFeedbackCreateRequest,
    ) -> CitizenFeedbackResponse:
        metadata = sanitize_metadata(
            {
                **redact_private_value(sanitize_metadata(request.metadata)),
                "scenario": redact_private_value(request.scenario),
                "risk_level": redact_private_value(request.risk_level),
                "related_turn_id": _related_turn(request.related_turn_id),
                "not_trusted_source_evidence": True,
            }
        )
        record = CitizenFeedbackRecord(
            user_id=request.user_id,
            session_id=request.session_id,
            category=request.category,
            message=redact_private_value(request.message),
            severity=request.severity,
            status="new",
            metadata=_without_none(metadata),
        )
        self._store_feedback(record)
        return CitizenFeedbackResponse(
            feedback_id=record.feedback_id,
            status=record.status or "new",
            created_at=record.created_at,
            safety_message=FEEDBACK_SAFETY_MESSAGE,
            stored=True,
        )

    def create_escalation(
        self,
        request: EscalationCreateRequest,
        *,
        workspace_ticket_id: str | None = None,
    ) -> EscalationResponse:
        metadata = sanitize_metadata(
            {
                **redact_private_value(sanitize_metadata(request.metadata)),
                "reason": request.reason,
                "urgency": request.urgency,
                "related_turn_id": _related_turn(request.related_turn_id),
                "user_provided_input": True,
                "not_trusted_source_evidence": True,
            }
        )
        # Only the server's workspace adapter supplies this linkage, never the API body.
        if workspace_ticket_id is not None:
            if not re.fullmatch(r"ticket-[a-f0-9]{32}", workspace_ticket_id):
                raise ValueError("Invalid server workspace ticket reference")
            metadata["workspace_ticket_id"] = workspace_ticket_id
        record = EscalationRequestRecord(
            user_id=request.user_id,
            session_id=request.session_id,
            scenario=redact_private_value(request.scenario),
            risk_level=redact_private_value(request.risk_level),
            summary=redact_private_value(request.summary),
            status="new",
            metadata=_without_none(metadata),
        )
        self._store_escalation(record)
        return EscalationResponse(
            escalation_id=record.escalation_id,
            status=record.status or "new",
            created_at=record.created_at,
            safety_message=NOT_EMERGENCY_DISPATCH_MESSAGE,
            not_emergency_dispatch=True,
            stored=True,
        )

    def list_feedback(
        self,
        status: str | None = None,
        limit: int = 50,
    ) -> list[CitizenFeedbackRecord]:
        if self.feedback_repository is not None:
            records = self.feedback_repository.list(status=status, limit=limit)
            return [_safe_feedback(record) for record in records]
        records = list(self._feedback_records.values())
        if status is not None:
            records = [record for record in records if record.status == status]
        return [_safe_feedback(record) for record in records[:limit]]

    def update_feedback_status(
        self,
        feedback_id: str,
        request: AdminQueueUpdateRequest,
    ) -> CitizenFeedbackRecord:
        record = self._get_feedback(feedback_id)
        metadata = _metadata_with_admin_note(record.metadata, request.note)
        updated = record.model_copy(
            update={"status": request.status, "metadata": metadata}
        )
        self._store_feedback(updated)
        return updated

    def list_escalations(
        self,
        status: str | None = None,
        limit: int = 50,
    ) -> list[EscalationRequestRecord]:
        if self.escalation_repository is not None:
            records = self.escalation_repository.list(status=status, limit=limit)
            return [_safe_escalation(record) for record in records]
        records = list(self._escalation_records.values())
        if status is not None:
            records = [record for record in records if record.status == status]
        return [_safe_escalation(record) for record in records[:limit]]

    def get_escalation(self, escalation_id: str) -> EscalationRequestRecord | None:
        if self.escalation_repository is not None:
            record = self.escalation_repository.get(escalation_id)
        else:
            record = self._escalation_records.get(escalation_id)
        return _safe_escalation(record) if record else None

    def find_workspace_ticket(
        self, owner: str, ticket_id: str
    ) -> EscalationRequestRecord | None:
        """Internal repair lookup: both server owner and server ticket ID must match."""
        if self.escalation_repository is not None:
            record = self.escalation_repository.find_workspace_ticket(owner, ticket_id)
            return _safe_escalation(record) if record else None
        return next(
            (
                record for record in self._escalation_records.values()
                if record.user_id == owner
                and record.metadata.get("workspace_ticket_id") == ticket_id
            ), None,
        )

    def update_escalation_status(
        self,
        escalation_id: str,
        request: AdminQueueUpdateRequest,
    ) -> EscalationRequestRecord:
        record = self._get_escalation(escalation_id)
        metadata = _metadata_with_admin_note(record.metadata, request.note)
        updated = record.model_copy(
            update={
                "status": request.status,
                "assigned_to": redact_private_value(
                    request.assigned_to or record.assigned_to,
                    preserve_references=True, key="actor_id",
                ),
                "metadata": metadata,
                "updated_at": utc_now(),
            }
        )
        self._store_escalation(updated)
        return updated

    def summarize(self) -> HumanSupportSummary:
        feedback = self.list_feedback(limit=10_000)
        escalations = self.list_escalations(limit=10_000)
        return HumanSupportSummary(
            feedback_count=len(feedback),
            escalation_count=len(escalations),
            urgent_escalation_count=sum(
                1
                for record in escalations
                if str(record.metadata.get("urgency", "")).casefold() == "urgent"
            ),
            open_feedback_count=sum(
                1 for record in feedback if (record.status or "new") in OPEN_STATUSES
            ),
            open_escalation_count=sum(
                1
                for record in escalations
                if (record.status or "new") in OPEN_STATUSES
            ),
            used_network=False,
            used_external_provider=False,
            warnings=[
                "Human support queue foundation only; no staffed operations or notifications.",
                "This queue is not emergency dispatch.",
            ],
        )

    def reset_for_tests(self) -> None:
        self._feedback_records.clear()
        self._escalation_records.clear()

    def _store_feedback(self, record: CitizenFeedbackRecord) -> None:
        if self.feedback_repository is not None:
            self.feedback_repository.add(record)
        else:
            self._feedback_records[record.feedback_id] = record

    def _store_escalation(self, record: EscalationRequestRecord) -> None:
        if self.escalation_repository is not None:
            self.escalation_repository.add(record)
        else:
            self._escalation_records[record.escalation_id] = record

    def _get_feedback(self, feedback_id: str) -> CitizenFeedbackRecord:
        if self.feedback_repository is not None:
            record = self.feedback_repository.get(feedback_id)
        else:
            record = self._feedback_records.get(feedback_id)
        if record is None:
            raise KeyError(f"Feedback record not found: {feedback_id}")
        return _safe_feedback(record)

    def _get_escalation(self, escalation_id: str) -> EscalationRequestRecord:
        if self.escalation_repository is not None:
            record = self.escalation_repository.get(escalation_id)
        else:
            record = self._escalation_records.get(escalation_id)
        if record is None:
            raise KeyError(f"Escalation request not found: {escalation_id}")
        return _safe_escalation(record)


def _metadata_with_admin_note(
    metadata: dict,
    note: str | None,
) -> dict:
    if not note:
        return _safe_metadata(metadata)
    return _safe_metadata({**metadata, "admin_note": note})


def _safe_metadata(metadata: dict) -> dict:
    cleaned = redact_private_value(sanitize_metadata(metadata))
    ticket_id = metadata.get("workspace_ticket_id")
    if isinstance(ticket_id, str) and re.fullmatch(r"ticket-[a-f0-9]{32}", ticket_id):
        cleaned["workspace_ticket_id"] = ticket_id
    related_turn = metadata.get("related_turn_id")
    if isinstance(related_turn, str) and _TRACE_UUID.fullmatch(related_turn):
        cleaned["related_turn_id"] = related_turn
    return cleaned


def _safe_feedback(record: CitizenFeedbackRecord) -> CitizenFeedbackRecord:
    return record.model_copy(update={
        "message": redact_private_value(record.message),
        "metadata": _safe_metadata(record.metadata),
    })


def _safe_escalation(record: EscalationRequestRecord) -> EscalationRequestRecord:
    return record.model_copy(update={
        "summary": redact_private_value(record.summary),
        "scenario": redact_private_value(record.scenario),
        "risk_level": redact_private_value(record.risk_level),
        "assigned_to": redact_private_value(
            record.assigned_to, preserve_references=True, key="actor_id",
        ),
        "metadata": _safe_metadata(record.metadata),
    })


def _without_none(metadata: dict) -> dict:
    return {key: value for key, value in metadata.items() if value is not None}
