from datetime import UTC, date, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from backend.app.checklist_engine.models import ChecklistProfileContext
from backend.app.domain.checklists import ChecklistGroup
from backend.app.domain.enums import LanguageCode, UserScenario
from backend.app.human_support.models import EscalationReason, EscalationUrgency, QueueStatus
from backend.app.schemas.chat import ChatResponse


def now() -> datetime:
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CreateRequest(StrictModel):
    client_request_id: str | None = Field(default=None, min_length=1, max_length=64)


class Context(StrictModel):
    display_name: str = Field(default="", max_length=100)
    position: str = Field(default="", max_length=100)
    city: str | None = Field(default=None, max_length=100)
    purpose: str | None = Field(default=None, max_length=300)
    institution: str | None = Field(default=None, max_length=200)
    deadline: date | None = None
    preferred_language: LanguageCode = LanguageCode.ru
    notes: str = Field(default="", max_length=2000)


class ContextPatch(StrictModel):
    display_name: str | None = Field(default=None, max_length=100)
    position: str | None = Field(default=None, max_length=100)
    city: str | None = Field(default=None, max_length=100)
    purpose: str | None = Field(default=None, max_length=300)
    institution: str | None = Field(default=None, max_length=200)
    deadline: date | None = None
    preferred_language: LanguageCode | None = None
    notes: str | None = Field(default=None, max_length=2000)


CaseStatus = Literal["open", "completed", "archived"]
TaskStatus = Literal["todo", "in_progress", "done", "skipped"]


class CaseCreate(CreateRequest):
    title: str = Field(min_length=1, max_length=200)
    scenario: UserScenario
    context: Context | None = None
    deadline: date | None = None
    use_profile_context: StrictBool = False


class CasePatch(StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    scenario: UserScenario | None = None
    context: ContextPatch | None = None
    deadline: date | None = None
    status: CaseStatus | None = None


class PlanCreate(CreateRequest):
    scenario: UserScenario
    language: LanguageCode = LanguageCode.ru
    use_profile_context: StrictBool = False
    overrides: ChecklistProfileContext = Field(default_factory=ChecklistProfileContext)


class TaskCreate(CreateRequest):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    due_at: date | None = None
    priority: int = Field(default=2, ge=1, le=3)


class TaskPatch(StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    due_at: date | None = None
    priority: int | None = Field(default=None, ge=1, le=3)
    status: TaskStatus | None = None


class Task(StrictModel):
    task_id: str = Field(default_factory=lambda: new_id("task"))
    title: str
    description: str = ""
    due_at: date | None = None
    priority: int = 2
    status: TaskStatus = "todo"
    template_key: str | None = None
    source_ids: list[str] = Field(default_factory=list)
    origin_trace_id: str | None = None
    community_source_ids: list[str] = Field(default_factory=list)
    group: ChecklistGroup = "optional"
    required_documents: list[str] = Field(default_factory=list)
    estimated_time: str | None = None
    scenario: UserScenario | None = None
    risk_level: str | None = None
    action: Literal["chat", "explain", "support"] = "chat"
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)


class MessageCreate(CreateRequest):
    text: str = Field(min_length=1, max_length=8000)
    kind: Literal["note", "user"] = "note"


class Message(StrictModel):
    message_id: str = Field(default_factory=lambda: new_id("message"))
    kind: Literal["note", "user", "assistant"]
    text: str
    trace_id: str | None = None
    source_ids: list[str] = Field(default_factory=list)
    response: ChatResponse | None = None
    created_at: datetime = Field(default_factory=now)
    not_trusted_evidence: Literal[True] = True


class DocumentCreate(CreateRequest):
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=12000)
    document_type: str = Field(default="notice", min_length=1, max_length=100)
    confirmed: bool = False


class Document(StrictModel):
    document_id: str = Field(default_factory=lambda: new_id("document"))
    title: str
    text: str
    document_type: str = "notice"
    confirmed: bool = False
    created_at: datetime = Field(default_factory=now)
    not_trusted_evidence: Literal[True] = True


class DocumentPatch(StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    text: str | None = Field(default=None, min_length=1, max_length=12000)
    confirmed: bool | None = None


class TimelineEvent(StrictModel):
    event_id: str = Field(default_factory=lambda: new_id("event"))
    event_type: str
    item_id: str | None = None
    summary: str
    created_at: datetime = Field(default_factory=now)


class WorkspaceCase(StrictModel):
    case_id: str = Field(default_factory=lambda: new_id("case"))
    title: str
    scenario: UserScenario
    context: Context = Field(default_factory=Context)
    deadline: date | None = None
    status: CaseStatus = "open"
    tasks: list[Task] = Field(default_factory=list)
    plan_warnings: list[str] = Field(default_factory=list)
    messages: list[Message] = Field(default_factory=list)
    documents: list[Document] = Field(default_factory=list)
    timeline: list[TimelineEvent] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)
    not_trusted_evidence: Literal[True] = True


class ChecklistCreate(StrictModel):
    language: LanguageCode | None = None


class SupportCreate(CreateRequest):
    case_id: str | None = Field(default=None, max_length=80)
    summary: str = Field(min_length=1, max_length=4000)
    reason: EscalationReason = "needs_human_help"
    urgency: EscalationUrgency = "normal"


class ReplyCreate(CreateRequest):
    text: str = Field(min_length=1, max_length=4000)


class SupportPatch(StrictModel):
    status: Literal["new", "closed"]


class OperatorReply(StrictModel):
    text: str = Field(min_length=1, max_length=4000)
    status: QueueStatus = "waiting_for_user"


class ConsulReply(CreateRequest):
    text: str = Field(min_length=1, max_length=4000)
    status: Literal["in_review", "waiting_for_user", "resolved"] = "waiting_for_user"


class ConsulStatus(StrictModel):
    status: Literal["in_review", "waiting_for_user", "resolved", "closed"]


class SupportReply(StrictModel):
    reply_id: str = Field(default_factory=lambda: new_id("reply"))
    role: Literal["citizen", "operator", "consul"]
    text: str
    created_at: datetime = Field(default_factory=now)
    responder_id: str | None = None  # Non-reversible server actor digest for audit.


class SupportTicket(StrictModel):
    ticket_id: str = Field(default_factory=lambda: new_id("ticket"))
    case_id: str | None = None
    escalation_id: str | None = None
    summary: str
    reason: EscalationReason
    urgency: EscalationUrgency
    status: QueueStatus = "new"
    replies: list[SupportReply] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)
    not_emergency_dispatch: Literal[True] = True
    staffed: Literal[False] = False
    queue_sync_pending: bool = False
    queue_status_available: bool = True
    status_actor_id: str | None = None


class CommunityCreate(CreateRequest):
    title: str = Field(min_length=1, max_length=200)
    scenario: UserScenario
    city: str | None = Field(default=None, max_length=100)
    language: LanguageCode = LanguageCode.ru
    situation: str = Field(min_length=1, max_length=2000)
    what_happened: str = Field(min_length=1, max_length=4000)
    what_helped: str | None = Field(default=None, max_length=2000)
    advice_for_others: str | None = Field(default=None, max_length=2000)
    tags: list[str] = Field(default_factory=list, max_length=12)
    allow_ai_retrieval: bool = False
    experience_date: date | None = None

    @model_validator(mode="after")
    def validate_tags(self):
        if any(not tag.strip() or len(tag) > 60 for tag in self.tags):
            raise ValueError("tags must contain 1-60 characters")
        return self


class CommunityDecision(StrictModel):
    action: Literal["approve", "reject"]
    reason: str = Field(min_length=1, max_length=2000)
    allow_ai_retrieval: bool = False


class WorkspaceRecord(StrictModel):
    owner: str
    profile: Context = Field(default_factory=Context)
    cases: dict[str, WorkspaceCase] = Field(default_factory=dict)
    tickets: dict[str, SupportTicket] = Field(default_factory=dict)
    # Post IDs associate current moderation state with its authenticated submitting owner.
    posts: dict[str, dict] = Field(default_factory=dict)
    requests: dict[str, dict[str, str]] = Field(default_factory=dict)
