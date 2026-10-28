"""Bounded, owner-scoped local workspace storage.

The lock serializes this app's updates. JSONL is a local single-process foundation,
not a distributed production database. Demo sessions are never persisted.
"""

import hashlib
import json
import re
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from fastapi import HTTPException

from backend.app.answer_quality.policies import is_synthetic_source
from backend.app.api_utils.identity_boundary import ResolvedIdentity, is_persistent_owner
from backend.app.checklist_engine.models import ChecklistGenerationRequest, ChecklistProfileContext
from backend.app.checklist_engine.service import ChecklistEngineService
from backend.app.config import Settings
from backend.app.domain.community import CommunityPost
from backend.app.domain.enums import ModerationStatus, RiskLevel, SourceType
from backend.app.domain.sources import is_retrievable_source
from backend.app.human_support.models import AdminQueueUpdateRequest, EscalationCreateRequest
from backend.app.human_support.service import HumanSupportService
from backend.app.memory.redaction import redact_sensitive_text
from backend.app.moderation.service import CommunityModerationService
from backend.app.persistence.errors import RecordNotFoundError
from backend.app.persistence.factory import build_community_post_repository
from backend.app.persistence.runtime_sources import sanitize_community_post
from backend.app.schemas.chat import ChatResponse
from backend.app.schemas.community import CommunityPostCreateRequest
from backend.app.services.community_service import CommunityService
from backend.app.source_registry.registry import SourceRegistry
from backend.app.workspace.models import (
    CaseCreate,
    CasePatch,
    ChecklistCreate,
    CommunityCreate,
    CommunityDecision,
    ConsulReply,
    Context,
    ContextPatch,
    Document,
    DocumentCreate,
    DocumentPatch,
    Message,
    MessageCreate,
    OperatorReply,
    PlanCreate,
    ReplyCreate,
    SupportCreate,
    SupportReply,
    SupportTicket,
    Task,
    TaskCreate,
    TaskPatch,
    TimelineEvent,
    WorkspaceCase,
    WorkspaceRecord,
    now,
)
from backend.app.workspace.storage import (
    WorkspaceCommitUncertain,
    WorkspaceRecoveryRequired,
    WorkspaceSnapshotStore,
)

RECORD_TYPE = "citizen_workspace"
_RAW_BINARY = re.compile(r"data:[^\s;,]+;base64,|[A-Za-z0-9+/]{400,}={0,2}", re.I)


def clean_text(value: str) -> str:
    if _RAW_BINARY.search(value) or "-----BEGIN " in value:
        raise HTTPException(422, "raw_images_or_key_material_not_allowed")
    return redact_sensitive_text(value)[0]


def sanitize_response(response: ChatResponse, *, case_id: str | None = None) -> ChatResponse:
    """Preserve server-created reference identifiers; redact all human-readable content."""
    identity_keys = {
        "trace_id",
        "case_id",
        "source_id",
        "source_ids",
        "citation_id",
        "citation_ids",
        "content_hash",
    }

    def redact(value, key=""):
        if key in {"session_id", "user_id", "owner", "actor_id"}:
            return None
        if isinstance(value, dict):
            return {k: redact(v, k) for k, v in value.items()}
        if isinstance(value, list):
            return [redact(item, key) for item in value]
        if isinstance(value, str):
            if key in identity_keys and re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", value):
                return value
            return clean_text(value)
        return value

    result = ChatResponse.model_validate(redact(response.model_dump(mode="json")))
    result.case_id = case_id
    result.session_id = None
    return result


def _clean(values: dict) -> dict:
    result = {}
    for key, value in values.items():
        if key == "client_request_id":
            continue
        if isinstance(value, str) and key != "case_id":
            result[key] = clean_text(value)
        elif isinstance(value, dict):
            result[key] = _clean(value)
        elif isinstance(value, list):
            result[key] = [clean_text(item) if isinstance(item, str) else item for item in value]
        else:
            result[key] = value
    return result


def _page(items: list, limit: int, offset: int, key: str) -> dict:
    return {
        key: items[offset : offset + limit],
        "total": len(items),
        "limit": limit,
        "offset": offset,
    }


class WorkspaceService:
    def __init__(self, settings: Settings, support: HumanSupportService | None = None):
        self.settings = settings
        self.support = support or HumanSupportService()
        self._lock = threading.RLock()
        self._sessions: dict[str, tuple[str, float]] = {}
        self._records: dict[str, WorkspaceRecord] = {}
        self._busy_cases: set[str] = set()
        self.store = (
            WorkspaceSnapshotStore(Path(settings.LOCAL_DATA_DIR) / "citizen_workspace.jsonl")
            if settings.ENABLE_LOCAL_PERSISTENCE
            else None
        )
        self.post_repository = (
            build_community_post_repository(settings.LOCAL_DATA_DIR)
            if settings.ENABLE_LOCAL_PERSISTENCE
            else None
        )
        if self.store:
            for state in self.store.load():
                self._records[state.owner] = state

    def issue_demo_session(self) -> str:
        with self._lock:
            current = time.monotonic()
            expired = [key for key, (_, until) in self._sessions.items() if until <= current]
            for key in expired:
                owner, _ = self._sessions.pop(key)
                self._records.pop(owner, None)
            if len(self._sessions) >= 128:
                raise HTTPException(429, "demo_session_limit")
            token = secrets.token_urlsafe(32)
            digest = hashlib.sha256(token.encode()).hexdigest()
            self._sessions[digest] = ("demo:" + secrets.token_hex(24), current + 12 * 3600)
            return token

    def demo_owner(self, token: str) -> str:
        with self._lock:
            if not 20 <= len(token) <= 128:
                raise HTTPException(401, "workspace_session_required")
            found = self._sessions.get(hashlib.sha256(token.encode()).hexdigest())
            if found is None or found[1] <= time.monotonic():
                raise HTTPException(401, "workspace_session_required")
            return found[0]

    def _record(self, owner: str) -> WorkspaceRecord:
        if self.store and self.store.blocked:
            raise HTTPException(503, "workspace_storage_recovery_required")
        return self._records.get(owner, WorkspaceRecord(owner=owner)).model_copy(deep=True)

    def _save(self, record: WorkspaceRecord, *, compact: bool = False) -> None:
        # Every commit now compacts atomically. Retain the private keyword used
        # by deletion callers; it no longer triggers fallible post-commit I/O.
        with self._lock:
            if self.store and is_persistent_owner(record.owner):
                pending = {**self._records, record.owner: record}
                self._publish(pending.values())
            self._records[record.owner] = record

    def _publish(self, records) -> None:
        try:
            self.store.publish(records)
        except WorkspaceRecoveryRequired as exc:
            raise HTTPException(503, "workspace_storage_recovery_required") from exc
        except WorkspaceCommitUncertain as exc:
            raise HTTPException(503, "workspace_save_unconfirmed") from exc
        except OSError as exc:
            raise HTTPException(503, "workspace_save_failed") from exc

    def _compact(self) -> None:
        """Use the same commit boundary, serialized with updates in this process."""
        with self._lock:
            if self.store:
                self._publish(self._records.values())

    @staticmethod
    def _case(record: WorkspaceRecord, case_id: str) -> WorkspaceCase:
        case = record.cases.get(case_id)
        if case is None:
            raise HTTPException(404, "case_not_found")
        return case

    @staticmethod
    def _ticket(record: WorkspaceRecord, ticket_id: str) -> SupportTicket:
        ticket = record.tickets.get(ticket_id)
        if ticket is None:
            raise HTTPException(404, "ticket_not_found")
        return ticket

    @staticmethod
    def _event(case: WorkspaceCase, event: str, summary: str, item_id: str | None = None):
        case.timeline.append(TimelineEvent(event_type=event, summary=summary, item_id=item_id))
        case.timeline = case.timeline[-500:]
        case.updated_at = now()

    def _not_busy(self, case_id: str):
        if case_id in self._busy_cases:
            raise HTTPException(409, "case_chat_in_progress")

    def _writable(self, case: WorkspaceCase, *, chat_append: bool = False):
        if not chat_append:
            self._not_busy(case.case_id)
        if case.status != "open":
            raise HTTPException(409, "reopen_case_before_editing")

    @contextmanager
    def chat_transaction(self, owner: str, case_id: str):
        """Reserve one case during generation without holding the workspace lock."""
        with self._lock:
            case = self._case(self._record(owner), case_id)
            self._writable(case)
            if len(case.messages) > 198:
                raise HTTPException(409, "workspace_item_limit")
            self._busy_cases.add(case_id)
        try:
            yield case
        finally:
            with self._lock:
                self._busy_cases.discard(case_id)

    @staticmethod
    def _limit(items, limit: int):
        if len(items) >= limit:
            raise HTTPException(409, "workspace_item_limit")

    @staticmethod
    def _request(
        record: WorkspaceRecord, operation: str, request, *, exclude_unset: bool = False,
    ) -> tuple[str, str, str | None]:
        key = getattr(request, "client_request_id", None)
        if not key:
            return "", "", None
        key = hashlib.sha256((operation + "\0" + key).encode()).hexdigest()
        body = request.model_dump(
            mode="json", exclude={"client_request_id"}, exclude_unset=exclude_unset,
        )
        if isinstance(request, CaseCreate) and not request.use_profile_context:
            # Old case retries did not serialize this new optional consent field.
            body.pop("use_profile_context", None)
        digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        previous = record.requests.get(key)
        if previous and previous["digest"] != digest:
            raise HTTPException(409, "idempotency_key_reused")
        return key, digest, previous["item_id"] if previous else None

    @staticmethod
    def _remember(record, key, digest, item_id):
        if key:
            record.requests[key] = {"digest": digest, "item_id": item_id}
            while len(record.requests) > 500:
                del record.requests[next(iter(record.requests))]

    def get_profile(self, owner: str) -> Context:
        with self._lock:
            return self._record(owner).profile

    def update_profile(self, owner: str, request: ContextPatch | None) -> Context:
        with self._lock:
            record = self._record(owner)
            values = record.profile.model_dump()
            if request is None:
                values = {}
            else:
                values.update(_clean(request.model_dump(exclude_unset=True)))
                if values.get("preferred_language") is None:
                    values.pop("preferred_language", None)
                if values.get("notes") is None:
                    values["notes"] = ""
                for field in ("display_name", "position"):
                    if values.get(field) is None:
                        values[field] = ""
            record.profile = Context.model_validate(values)
            self._save(record, compact=request is None)
            return record.profile.model_copy(deep=True)

    def list_cases(self, owner: str, status: str | None = None, limit=30, offset=0) -> dict:
        with self._lock:
            cases = list(self._record(owner).cases.values())
            cases = [case for case in cases if status is None or case.status == status]
            cases.sort(key=lambda case: case.updated_at, reverse=True)
            page = _page(cases, limit, offset, "cases")
            # List cards must not replicate every document or complete assistant response.
            page["cases"] = [
                {
                    **case.model_dump(
                        mode="json", exclude={"messages", "documents", "timeline", "tasks"}
                    ),
                    "tasks": [
                        task.model_dump(
                            mode="json",
                            include={
                                "task_id",
                                "title",
                                "status",
                                "priority",
                                "due_at",
                            },
                        )
                        for task in case.tasks
                    ],
                    "message_count": len(case.messages),
                    "document_count": len(case.documents),
                }
                for case in page["cases"]
            ]
            return page

    def get_case(self, owner: str, case_id: str) -> WorkspaceCase:
        with self._lock:
            return self._case(self._record(owner), case_id)

    def create_case(self, owner: str, request: CaseCreate) -> WorkspaceCase:
        with self._lock:
            record = self._record(owner)
            key, digest, previous = self._request(record, "case", request)
            if previous:
                return self._case(record, previous)
            self._limit(record.cases, 100)
            fields = _clean(request.model_dump(exclude={"context", "use_profile_context"}))
            values = {
                field: getattr(record.profile, field)
                for field in ChecklistProfileContext.model_fields
            } if request.use_profile_context else {}
            if request.context is not None:
                values.update(request.context.model_dump(exclude_unset=True))
            fields["context"] = Context.model_validate(_clean(values))
            case = WorkspaceCase(**fields)
            record.cases[case.case_id] = case
            self._event(case, "created", "case_created")
            self._remember(record, key, digest, case.case_id)
            self._save(record)
            return case.model_copy(deep=True)

    def update_case(self, owner: str, case_id: str, request: CasePatch) -> WorkspaceCase:
        with self._lock:
            record = self._record(owner)
            case = self._case(record, case_id)
            self._not_busy(case_id)
            fields = _clean(request.model_dump(exclude_unset=True))
            if fields.get("status") == "completed" and any(
                task.status in {"todo", "in_progress"} for task in case.tasks
            ):
                raise HTTPException(409, "complete_or_skip_pending_tasks")
            context = fields.pop("context", None)
            if context is not None:
                context_values = {**case.context.model_dump(), **context}
                if context_values.get("notes") is None:
                    context_values["notes"] = ""
                if context_values.get("preferred_language") is None:
                    context_values.pop("preferred_language", None)
                fields["context"] = Context.model_validate(context_values)
            fields = {
                key: value
                for key, value in fields.items()
                if value is not None or key == "deadline"
            }
            updated = WorkspaceCase.model_validate({**case.model_dump(), **fields})
            if updated != case:
                event = (
                    "reopened" if case.status != "open" and updated.status == "open" else "updated"
                )
                self._event(updated, event, "case_" + event)
                record.cases[case_id] = updated
                self._save(record)
            return updated.model_copy(deep=True)

    def delete_case(self, owner: str, case_id: str):
        with self._lock:
            record = self._record(owner)
            self._case(record, case_id)
            self._not_busy(case_id)
            del record.cases[case_id]
            for ticket in record.tickets.values():
                if ticket.case_id == case_id:
                    ticket.case_id = None
            self._save(record, compact=True)

    def add_task(self, owner: str, case_id: str, request: TaskCreate) -> WorkspaceCase:
        with self._lock:
            record = self._record(owner)
            case = self._case(record, case_id)
            key, digest, previous = self._request(record, case_id + ":task", request)
            if previous:
                return case
            self._writable(case)
            self._limit(case.tasks, 200)
            task = Task(**_clean(request.model_dump()))
            case.tasks.append(task)
            self._event(case, "task_created", "task_created", task.task_id)
            self._remember(record, key, digest, task.task_id)
            self._save(record)
            return case.model_copy(deep=True)

    def update_task(self, owner, case_id, task_id, request: TaskPatch) -> WorkspaceCase:
        with self._lock:
            record = self._record(owner)
            case = self._case(record, case_id)
            self._writable(case)
            task = next((item for item in case.tasks if item.task_id == task_id), None)
            if task is None:
                raise HTTPException(404, "task_not_found")
            fields = _clean(request.model_dump(exclude_unset=True))
            fields = {
                key: value for key, value in fields.items() if value is not None or key == "due_at"
            }
            updated = Task.model_validate({**task.model_dump(), **fields})
            if updated != task:
                if updated.title != task.title or updated.description != task.description:
                    # A user's rewritten instruction is not the model's verified claim.
                    updated.source_ids = []
                updated.updated_at = now()
                case.tasks[case.tasks.index(task)] = updated
                self._event(case, "task_updated", "task_" + updated.status, task_id)
                self._save(record)
            return case.model_copy(deep=True)

    def create_plan(self, owner: str, request: PlanCreate) -> WorkspaceCase:
        with self._lock:
            record = self._record(owner)
            key, digest, previous = self._request(record, "plan", request, exclude_unset=True)
            if previous:
                return self._case(record, previous).model_copy(deep=True)
            self._limit(record.cases, 100)
            values = {
                field: getattr(record.profile, field)
                for field in ChecklistProfileContext.model_fields
            } if request.use_profile_context else {}
            values.update(request.overrides.model_dump(exclude_unset=True))
            snapshot = Context.model_validate(_clean({
                **values, "preferred_language": request.language,
            }))
            case = WorkspaceCase(
                title="Checklist", scenario=request.scenario, context=snapshot,
                deadline=snapshot.deadline,
            )
            result = self._plan(case, request.language)
            case.title = result.checklist.title
            self._append_plan(case, result)
            record.cases[case.case_id] = case
            self._event(case, "created", "case_created")
            self._remember(record, key, digest, case.case_id)
            self._save(record)
            return case.model_copy(deep=True)

    @staticmethod
    def _plan(case, language):
        risk = RiskLevel({
            "medical": "medical_sensitive", "work": "work_status_sensitive",
            "emergency": "emergency", "documents": "legal_sensitive",
        }.get(case.scenario.value, "normal"))
        return ChecklistEngineService().generate(ChecklistGenerationRequest(
            scenario=case.scenario, language=language, risk_level=risk,
            approved_context=ChecklistProfileContext(**{
                field: getattr(case.context, field)
                for field in ChecklistProfileContext.model_fields
            }), preparation_only=True,
        ))

    @staticmethod
    def _append_plan(case, result):
        additions = []
        for item in result.checklist.items:
            template_key = case.scenario.value + ":" + item.item_id.removeprefix(
                case.scenario.value + "-",
            )
            if any(task.template_key == template_key for task in case.tasks):
                continue
            additions.append(Task(
                title=clean_text(item.title), description=clean_text(item.description or ""),
                due_at=case.deadline or case.context.deadline, priority=item.priority,
                template_key=template_key, group=item.group, scenario=item.scenario,
                risk_level=item.risk_level.value, action=item.action,
                # Preparation copy has no reviewed passage bindings. Never promote
                # selected IDs or profile claims into factual plan citations/details.
                source_ids=[], community_source_ids=[], required_documents=[], estimated_time=None,
            ))
        if len(case.tasks) + len(additions) > 200:
            raise HTTPException(409, "workspace_limit_reached")
        changed = bool(additions) or case.plan_warnings != result.warnings
        case.tasks.extend(additions)
        case.plan_warnings = result.warnings
        return changed

    def generate_checklist(
        self, owner, case_id, request: ChecklistCreate,
        source_registry: SourceRegistry | None = None,
    ) -> WorkspaceCase:
        with self._lock:
            record = self._record(owner)
            case = self._case(record, case_id)
            self._writable(case)
            result = self._plan(case, request.language or case.context.preferred_language)
            changed = self._append_plan(case, result)
            if source_registry is not None:
                from backend.app.workspace.answer_tasks import append_answer_tasks

                changed = append_answer_tasks(case, source_registry) or changed
            if changed:
                self._event(case, "checklist_created", "checklist_created")
                self._save(record)
            return case.model_copy(deep=True)

    def add_message(self, owner, case_id, request: MessageCreate) -> WorkspaceCase:
        with self._lock:
            record = self._record(owner)
            case = self._case(record, case_id)
            key, digest, previous = self._request(record, case_id + ":message", request)
            if previous:
                return case
            self._writable(case)
            self._limit(case.messages, 200)
            message = Message(**_clean(request.model_dump()))
            case.messages.append(message)
            self._event(case, "message_added", "message_added", message.message_id)
            self._remember(record, key, digest, message.message_id)
            self._save(record)
            return case.model_copy(deep=True)

    def append_exchange(
        self, owner: str, case_id: str, request_message: str, response, *, city: str | None = None,
    ):
        """Server-only hook: use AFTER answer delivery verification, never as evidence."""
        with self._lock:
            record = self._record(owner)
            case = self._case(record, case_id)
            self._writable(case, chat_append=True)
            if any(message.trace_id == response.trace_id for message in case.messages):
                return case
            if len(case.messages) > 198:
                raise HTTPException(409, "workspace_item_limit")
            if not case.messages and not case.context.city and city:
                # Only the first owned server turn can fill an empty case city.
                # Explicit case input and later corrections always win.
                case.context.city = clean_text(city)[:100]
            case.messages.extend(
                [
                    Message(
                        kind="user", text=clean_text(request_message), trace_id=response.trace_id
                    ),
                    Message(
                        kind="assistant",
                        text=clean_text(response.answer)[:24000],
                        trace_id=response.trace_id,
                        source_ids=list(dict.fromkeys(c.source_id for c in response.citations))[
                            :20
                        ],
                        response=sanitize_response(response, case_id=case_id),
                    ),
                ]
            )
            self._event(case, "exchange_added", "exchange_added", response.trace_id)
            self._save(record)
            return case.model_copy(deep=True)

    def add_document(self, owner, case_id, request: DocumentCreate) -> WorkspaceCase:
        with self._lock:
            record = self._record(owner)
            case = self._case(record, case_id)
            key, digest, previous = self._request(record, case_id + ":document", request)
            if previous:
                return case
            self._writable(case)
            self._limit(case.documents, 30)
            document = Document(**_clean(request.model_dump()))
            case.documents.append(document)
            self._event(case, "document_added", "document_added", document.document_id)
            self._remember(record, key, digest, document.document_id)
            self._save(record)
            return case.model_copy(deep=True)

    def update_document(self, owner, case_id, document_id, request: DocumentPatch | None):
        with self._lock:
            record = self._record(owner)
            case = self._case(record, case_id)
            self._writable(case)
            document = next(
                (item for item in case.documents if item.document_id == document_id), None
            )
            if document is None:
                raise HTTPException(404, "document_not_found")
            if request is None:
                case.documents.remove(document)
            else:
                fields = {
                    k: v
                    for k, v in _clean(request.model_dump(exclude_unset=True)).items()
                    if v is not None
                }
                updated = Document.model_validate({**document.model_dump(), **fields})
                if updated == document:
                    return case
                case.documents[case.documents.index(document)] = updated
            self._event(case, "document_updated", "document_updated", document_id)
            self._save(record, compact=True)
            return case.model_copy(deep=True)

    def create_ticket(self, owner: str, request: SupportCreate) -> SupportTicket:
        with self._lock:
            record = self._record(owner)
            key, digest, previous = self._request(record, "support", request)
            if previous:
                return self._ensure_ticket_queue(owner, previous)
            case = self._case(record, request.case_id) if request.case_id else None
            if case:
                self._not_busy(case.case_id)
            self._limit(record.tickets, 100)
            ticket = SupportTicket(**_clean(request.model_dump()))
            ticket.queue_sync_pending = is_persistent_owner(owner)
            record.tickets[ticket.ticket_id] = ticket
            if case:
                self._event(case, "support_requested", "support_requested", ticket.ticket_id)
            self._remember(record, key, digest, ticket.ticket_id)
            # The owned ticket is authoritative. A failed primary write must never
            # create an orphan in the shared queue.
            self._save(record)
            return self._ensure_ticket_queue(owner, ticket.ticket_id)

    def _ensure_ticket_queue(self, owner: str, ticket_id: str) -> SupportTicket:
        record = self._record(owner)
        ticket = self._ticket(record, ticket_id)
        if not is_persistent_owner(owner) or not ticket.queue_sync_pending:
            return ticket
        try:
            # A queue write may have succeeded before the link snapshot failed.
            # Recover by a stable, owner-scoped workspace ID instead of duplicating it.
            existing = self.support.find_workspace_ticket(owner, ticket.ticket_id)
            if existing is None:
                case = record.cases.get(ticket.case_id) if ticket.case_id else None
                existing = self.support.create_escalation(
                    EscalationCreateRequest(
                        user_id=owner,
                        summary=ticket.summary,
                        reason=ticket.reason,
                        urgency=ticket.urgency,
                        scenario=case.scenario.value if case else None,
                    ),
                    workspace_ticket_id=ticket.ticket_id,
                )
            ticket.escalation_id = existing.escalation_id
            if existing.status != ticket.status:
                self.support.update_escalation_status(
                    ticket.escalation_id, AdminQueueUpdateRequest(status=ticket.status)
                )
            ticket.queue_sync_pending = False
            ticket.queue_status_available = True
            self._save(record)
            return ticket.model_copy(deep=True)
        except (OSError, sqlite3.Error):
            # The primary ticket and retry marker are already committed. Reads or
            # an idempotent retry can repair the secondary store without data loss.
            ticket = self._ticket(self._record(owner), ticket_id)
            ticket.queue_status_available = False
            return ticket

    def _sync_ticket(self, ticket: SupportTicket):
        if ticket.escalation_id and not ticket.queue_sync_pending:
            try:
                existing = self.support.get_escalation(ticket.escalation_id)
            except (OSError, sqlite3.Error):
                ticket.queue_status_available = False
                return
            ticket.queue_status_available = existing is not None
            if existing and existing.status:
                ticket.status = existing.status

    def list_tickets(self, owner, limit=30, offset=0) -> dict:
        with self._lock:
            tickets = [
                self._ensure_ticket_queue(owner, ticket_id)
                for ticket_id in self._record(owner).tickets
            ]
            for ticket in tickets:
                self._sync_ticket(ticket)
            tickets.sort(key=lambda ticket: ticket.updated_at, reverse=True)
            return _page(tickets, limit, offset, "tickets")

    def get_ticket(self, owner, ticket_id):
        with self._lock:
            ticket = self._ensure_ticket_queue(owner, ticket_id)
            self._sync_ticket(ticket)
            return ticket

    def reply_ticket(self, owner, ticket_id, request: ReplyCreate) -> SupportTicket:
        with self._lock:
            record = self._record(owner)
            ticket = self._ticket(record, ticket_id)
            key, digest, previous = self._request(record, ticket_id + ":reply", request)
            if previous:
                return self._ensure_ticket_queue(owner, ticket_id)
            self._sync_ticket(ticket)
            if not ticket.queue_status_available:
                raise HTTPException(503, "support_queue_status_unavailable")
            if ticket.status in {"closed", "resolved"}:
                raise HTTPException(409, "reopen_ticket_before_replying")
            self._limit(ticket.replies, 100)
            reply = SupportReply(role="citizen", text=clean_text(request.text))
            ticket.replies.append(reply)
            ticket.status = "new"
            ticket.updated_at = now()
            ticket.queue_sync_pending = is_persistent_owner(owner)
            self._remember(record, key, digest, reply.reply_id)
            self._save(record)
            return self._ensure_ticket_queue(owner, ticket_id)

    def update_ticket(self, owner, ticket_id, status):
        with self._lock:
            record = self._record(owner)
            ticket = self._ticket(record, ticket_id)
            ticket.status = status
            ticket.updated_at = now()
            ticket.queue_sync_pending = is_persistent_owner(owner)
            self._save(record)
            return self._ensure_ticket_queue(owner, ticket_id)

    def operator_tickets(self, limit=30, offset=0):
        with self._lock:
            tickets = [
                self._ensure_ticket_queue(owner, ticket.ticket_id)
                for owner, record in self._records.items()
                if is_persistent_owner(owner)
                for ticket in record.tickets.values()
            ]
            for ticket in tickets:
                self._sync_ticket(ticket)
            return _page(
                sorted(tickets, key=lambda t: t.updated_at, reverse=True), limit, offset, "tickets"
            )

    @staticmethod
    def _consul_view(ticket: SupportTicket) -> dict:
        # A request shares its submitted summary and replies, never the citizen's
        # private profile, linked case, documents, notes or authentication IDs.
        return ticket.model_dump(mode="json", include={
            "ticket_id", "summary", "reason", "urgency", "status", "created_at", "updated_at",
            "replies", "not_emergency_dispatch", "staffed",
        }, exclude={"replies": {"__all__": {"responder_id"}}})

    def _ticket_owner(self, actor: ResolvedIdentity, ticket_id: str) -> str:
        owner = next((owner for owner, record in self._records.items()
                      if actor.allows_queue_owner(owner) and ticket_id in record.tickets), None)
        if owner is None:
            raise HTTPException(404, "ticket_not_found")
        return owner

    def consul_tickets(self, actor: ResolvedIdentity, status=None, limit=20, offset=0) -> dict:
        with self._lock:
            # Page after filtering all owned requests, not the first admin page.
            tickets = [self._ensure_ticket_queue(owner, ticket_id)
                       for owner, record in self._records.items() if actor.allows_queue_owner(owner)
                       for ticket_id in record.tickets]
            for ticket in tickets:
                self._sync_ticket(ticket)
            tickets.sort(key=lambda ticket: ticket.updated_at, reverse=True)
            return _page([self._consul_view(t) for t in tickets
                          if status is None or t.status == status], limit, offset, "tickets")

    def consul_ticket(self, actor: ResolvedIdentity, ticket_id: str) -> dict:
        with self._lock:
            return self._consul_view(
                self.get_ticket(self._ticket_owner(actor, ticket_id), ticket_id),
            )

    def consul_reply(self, actor: ResolvedIdentity, ticket_id: str, request: ConsulReply) -> dict:
        with self._lock:
            owner = self._ticket_owner(actor, ticket_id)
            record = self._record(owner)
            ticket = self._ticket(record, ticket_id)
            key, digest, previous = self._request(
                record, ticket_id + ":consul:" + actor.actor_id, request,
            )
            if previous:
                return self.consul_ticket(actor, ticket_id)
            self._sync_ticket(ticket)
            if not ticket.queue_status_available:
                raise HTTPException(503, "support_queue_status_unavailable")
            if ticket.status in {"closed", "resolved"}:
                raise HTTPException(409, "reopen_ticket_before_replying")
            self._limit(ticket.replies, 100)
            actor_digest = hashlib.sha256(actor.actor_id.encode()).hexdigest()
            reply = SupportReply(
                role="consul", text=clean_text(request.text), responder_id=actor_digest,
            )
            ticket.replies.append(reply)
            ticket.status = request.status
            ticket.status_actor_id = actor_digest
            ticket.updated_at = now()
            ticket.queue_sync_pending = True
            self._remember(record, key, digest, reply.reply_id)
            self._save(record)
            return self._consul_view(self._ensure_ticket_queue(owner, ticket_id))

    def consul_status(self, actor: ResolvedIdentity, ticket_id: str, status: str) -> dict:
        with self._lock:
            owner = self._ticket_owner(actor, ticket_id)
            record = self._record(owner)
            ticket = self._ticket(record, ticket_id)
            self._sync_ticket(ticket)
            if not ticket.queue_status_available:
                raise HTTPException(503, "support_queue_status_unavailable")
            if ticket.status == status:
                return self._consul_view(ticket)
            ticket.status = status
            ticket.status_actor_id = hashlib.sha256(actor.actor_id.encode()).hexdigest()
            ticket.updated_at = now()
            ticket.queue_sync_pending = True
            self._save(record)
            return self._consul_view(self._ensure_ticket_queue(owner, ticket_id))

    def operator_reply(self, ticket_id: str, request: OperatorReply):
        with self._lock:
            owner = next(
                (
                    key
                    for key, record in self._records.items()
                    if is_persistent_owner(key) and ticket_id in record.tickets
                ),
                None,
            )
            if owner is None:
                raise HTTPException(404, "ticket_not_found")
            record = self._record(owner)
            ticket = self._ticket(record, ticket_id)
            self._limit(ticket.replies, 100)
            ticket.replies.append(SupportReply(role="operator", text=clean_text(request.text)))
            ticket.status = request.status
            ticket.updated_at = now()
            ticket.queue_sync_pending = True
            self._save(record)
            return self._ensure_ticket_queue(owner, ticket_id)

    def create_post(self, owner: str, request: CommunityCreate) -> dict:
        with self._lock:
            record = self._record(owner)
            key, digest, previous = self._request(record, "community", request)
            if previous:
                return self._post_view(self._ensure_post_repository(owner, previous), True)
            self._limit(record.posts, 100)
            fields = _clean(request.model_dump(exclude={"experience_date"}))
            requested_consent = fields.pop("allow_ai_retrieval")
            post = (
                CommunityService(moderation_service=CommunityModerationService())
                .create_post(
                    CommunityPostCreateRequest(**fields),
                )
                .post
            )
            # Author identity and trust never come from client profile/role claims.
            post.author.contributor_id = (
                "workspace-" + hashlib.sha256(owner.encode()).hexdigest()[:32]
            )
            post.ai_retrieval_consent = requested_consent
            record.posts[post.post_id] = {
                "post": post.model_dump(mode="json"),
                "requested_ai_consent": requested_consent,
                "experience_date": request.experience_date.isoformat()
                if request.experience_date
                else None,
                "repository_sync_pending": bool(
                    is_persistent_owner(owner) and self.post_repository
                ),
            }
            self._remember(record, key, digest, post.post_id)
            self._save(record)
            return self._post_view(self._ensure_post_repository(owner, post.post_id), True)

    def _ensure_post_repository(
        self, owner: str, post_id: str, *, explicit_approval: bool = False
    ) -> dict:
        record = self._record(owner)
        stored = record.posts[post_id]
        if not stored.get("repository_sync_pending") or self.post_repository is None:
            return stored
        try:
            post = CommunityPost.model_validate(stored["post"])
            try:
                current = self.post_repository.get_post(post_id)
            except RecordNotFoundError:
                current = None
            if (
                not explicit_approval
                and current is not None
                and (
                    current.moderation_status in {
                        ModerationStatus.rejected,
                        ModerationStatus.flagged,
                        ModerationStatus.needs_review,
                    }
                    or (
                        current.moderation_status == ModerationStatus.approved
                        and not current.allow_ai_retrieval
                        and post.allow_ai_retrieval
                    )
                )
            ):
                # A later review may suspend publication or AI retrieval in the
                # secondary registry while this approval is still pending. Reads
                # and creation retries must preserve that more restrictive state.
                stored["post"] = current.model_dump(mode="json")
            else:
                self.post_repository.save_post(post)
            stored["repository_sync_pending"] = False
            self._save(record)
            return stored
        except OSError:
            return self._record(owner).posts[post_id]

    def _post_view(self, stored: dict, own: bool) -> dict:
        post = CommunityPost.model_validate(stored["post"])
        repository_status_available = True
        if self.post_repository:
            try:
                matching = self.post_repository.get_post(post.post_id)
            except RecordNotFoundError:
                matching = None
            except OSError:
                matching = None
                repository_status_available = False
            if matching:
                post = matching
            elif (
                not repository_status_available
                and post.moderation_status == ModerationStatus.approved
            ):
                post = post.model_copy(update={
                    "moderation_status": ModerationStatus.needs_review,
                    "allow_ai_retrieval": False,
                })
        post = sanitize_community_post(post)
        values = post.model_dump(mode="json", exclude={"author"})
        values.update(
            is_own=own,
            is_synthetic="synthetic" in json.dumps(values).casefold(),
            experience_date=stored.get("experience_date"),
            requested_ai_consent=stored.get("requested_ai_consent", False),
            repository_sync_pending=stored.get("repository_sync_pending", False),
            repository_status_available=repository_status_available,
        )
        return values

    def list_posts(
        self,
        owner,
        mine=False,
        scenario=None,
        city=None,
        language=None,
        query=None,
        limit=30,
        offset=0,
    ):
        with self._lock:
            own = self._record(owner).posts
            if mine:
                posts = [
                    self._post_view(self._ensure_post_repository(owner, post_id), True)
                    for post_id in own
                ]
            else:
                registry = SourceRegistry.from_data_dir()
                current = {p.post_id: p for p in registry.approved_community_posts()}
                for record_owner, record in self._records.items():
                    if is_persistent_owner(record_owner):
                        current.update(
                            {
                                post_id: CommunityPost.model_validate(stored["post"])
                                for post_id, stored in record.posts.items()
                            }
                        )
                if self.post_repository:
                    try:
                        current.update({p.post_id: p for p in self.post_repository.list_posts()})
                    except OSError:
                        # Per-post views below fail closed when current moderation
                        # state cannot be read; never publish stale approvals.
                        pass
                # Legacy approved rows must pass the same safety gate as the
                # public community API; owners can still inspect their own posts.
                moderator = CommunityModerationService()
                posts = [
                    self._post_view({"post": p.model_dump(mode="json")}, p.post_id in own)
                    for p in current.values()
                    if p.moderation_status == ModerationStatus.approved
                    and not moderator.moderate_post(p).findings
                ]
                posts = [p for p in posts if p["moderation_status"] == "approved"]
            posts = [p for p in posts if _matches(p, scenario, city, language, query)]
            posts.sort(key=lambda p: p["created_at"], reverse=True)
            return _page(posts, limit, offset, "posts")

    def operator_posts(self, limit=30, offset=0):
        with self._lock:
            posts = [
                self._post_view(stored, False)
                for owner, record in self._records.items()
                if is_persistent_owner(owner)
                for stored in record.posts.values()
            ]
            return _page(posts, limit, offset, "posts")

    def decide_post(self, post_id: str, request: CommunityDecision):
        with self._lock:
            owner = next(
                (
                    key
                    for key, record in self._records.items()
                    if is_persistent_owner(key) and post_id in record.posts
                ),
                None,
            )
            if owner is None:
                raise HTTPException(404, "post_not_found")
            record = self._record(owner)
            stored = record.posts[post_id]
            post = CommunityPost.model_validate(stored["post"])
            if request.action == "approve":
                moderation = CommunityModerationService().moderate_post(post)
                if moderation.findings:
                    raise HTTPException(409, "post_requires_safety_revision")
                if request.allow_ai_retrieval and not stored["requested_ai_consent"]:
                    raise HTTPException(409, "author_ai_consent_required")
                if request.allow_ai_retrieval and self.post_repository is None:
                    raise HTTPException(409, "durable_retrieval_repository_required")
            post.moderation_status = (
                ModerationStatus.approved
                if request.action == "approve"
                else ModerationStatus.rejected
            )
            post.allow_ai_retrieval = request.action == "approve" and request.allow_ai_retrieval
            stored["post"] = post.model_dump(mode="json")
            stored["moderation_reason"] = clean_text(request.reason)
            stored["repository_sync_pending"] = self.post_repository is not None
            if request.action == "reject" and self.post_repository:
                # Revocation fails closed: a failed primary snapshot may not leave
                # a previously approved post retrievable in the secondary registry.
                self.post_repository.save_post(post)
                stored["repository_sync_pending"] = False
            self._save(record)
            return self._post_view(
                self._ensure_post_repository(
                    owner, post_id, explicit_approval=request.action == "approve"
                ), False,
            )

    def library(
        self,
        registry: SourceRegistry,
        scenario=None,
        city=None,
        query=None,
        include_demo=False,
        limit=30,
        offset=0,
    ) -> dict:
        sources, demo = [], []
        for source in registry.all_sources():
            if source.source_type not in {SourceType.official, SourceType.curated_guide}:
                continue
            if not is_retrievable_source(source):
                continue
            synthetic = is_synthetic_source(source)
            reviewed = source.last_reviewed_at or source.reviewed_at
            if not synthetic and (reviewed is None or not source.reviewed_by):
                continue
            item = source.model_dump(mode="json", exclude={"reviewed_by"})
            item["title"] = clean_text(item["title"])
            item["content"] = clean_text(item.get("content") or "")[:12000]
            item.update(
                is_synthetic=synthetic,
                approved_official=(not synthetic and source.source_type == SourceType.official),
                reviewed_at=reviewed.isoformat() if reviewed else None,
            )
            if _matches(item, scenario, city, None, query):
                if synthetic:
                    item["source_type"] = "synthetic_demo"
                    demo.append(item)
                else:
                    sources.append(item)
        return {
            **_page(sources, limit, offset, "sources"),
            "demo_sources": demo[:limit] if include_demo else [],
            "coverage_complete": False,
        }


def _matches(item, scenario, city, language, query):
    return (
        (scenario is None or item.get("scenario") == scenario)
        and (city is None or city.casefold() in (item.get("city") or "").casefold())
        and (language is None or item.get("language") == language)
        and (query is None or query.casefold() in json.dumps(item, ensure_ascii=False).casefold())
    )
