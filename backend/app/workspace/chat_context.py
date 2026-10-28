"""Derive a private conversation from an owner-checked case, never retrieval evidence."""

import hashlib

from backend.app.agent.classification import classify_risk, classify_scenario
from backend.app.domain.enums import UserScenario
from backend.app.memory.models import ChecklistProgressMemory, ContextMessage, FollowUpContext
from backend.app.schemas.chat import ChatRequest
from backend.app.workspace.models import Context, WorkspaceCase


def profile_fields(profile: Context) -> dict[str, str]:
    """Only task-relevant, bounded private data; never names, roles or free notes."""
    return {
        key: str(value) for key, value in profile.model_dump(mode="json").items()
        if key in {"purpose", "institution", "deadline"} and value
    }


def build_profile_context(profile: Context, request: ChatRequest) -> FollowUpContext:
    scenario = classify_scenario(request.user_message)
    return FollowUpContext(
        session_id=request.session_id or "", active_scenario=scenario.value,
        active_risk_level=classify_risk(request.user_message, scenario).value,
        preferred_language=request.preferred_language.value,
        city=request.city or profile.city, recent_summary="",
        task_context=profile_fields(profile),
        warnings=["profile_material_is_untrusted_user_context"],
    )


def case_session(owner: str, case_id: str) -> str:
    return "case-" + hashlib.sha256((owner + "\0" + case_id).encode()).hexdigest()


def build_case_context(owner: str, case: WorkspaceCase, request: ChatRequest) -> FollowUpContext:
    current = classify_scenario(request.user_message)
    generic_document_question = current == UserScenario.documents and any(
        term in request.user_message.casefold()
        for term in (
            "what documents",
            "which documents",
            "какие документы",
            "какие бумаги",
            "қандай құжат",
            "什么材料",
            "哪些材料",
            "什么文件",
        )
    )
    previous = next((m.response.scenario for m in reversed(case.messages)
                     if m.kind == "assistant" and m.response), case.scenario)
    active = previous if request.use_conversation_context else case.scenario
    compatible = current in {UserScenario.unclear, active} or generic_document_question
    scenario = active if compatible else current
    relevant = case.messages[-6:] if (
        (compatible or request.use_conversation_context) and not request.reset_context
    ) else []
    recent = [
        ContextMessage(
            role="assistant" if message.kind == "assistant" else "user",
            text=message.text[:4000],
            truncated=len(message.text) > 4000,
        )
        for message in relevant
        if message.kind != "note"
    ]
    earlier_questions = " ".join(
        m.text[:2000] for m in relevant if m.kind == "user"
    ) if compatible else ""
    risk = classify_risk(earlier_questions + " " + request.user_message, scenario)
    fields = profile_fields(case.context)
    if case.context.notes:
        fields["notes"] = case.context.notes
    fields["deadline"] = str(case.deadline or case.context.deadline or "")
    fields["tasks"] = "\n".join(
        f"{task.status}: {task.title}; due={task.due_at or ''}; {task.description[:200]}"
        for task in case.tasks[:20]
    )[:4000]
    fields["documents"] = "\n".join(
        f"{document.title}: {document.text[:2000]}"
        for document in case.documents[-3:]
        if document.confirmed
    )[:6000]
    latest_assistant_message = next((
        message
        for message in reversed(case.messages)
        if message.kind == "assistant" and message.response
    ), None)
    latest_mode = (
        latest_assistant_message.response.metadata.get("assistant_mode")
        if latest_assistant_message else None
    )
    active_assistant_mode = (
        latest_mode if latest_mode in {"dialogue", "translation", "document_qa"} else None
    )
    if active_assistant_mode:
        fields["active_assistant_mode"] = active_assistant_mode
    if latest_assistant_message:
        active_writing_request = (
            latest_assistant_message.response.metadata.get("active_writing_request") is True
            if latest_mode == "dialogue"
            else False
        )
        fields["active_writing_request"] = (
            "true" if active_writing_request else "false"
        )
    return FollowUpContext(
        session_id=case_session(owner, case.case_id),
        active_scenario=scenario.value,
        active_risk_level=risk.value,
        preferred_language=request.preferred_language.value,
        city=case.context.city,
        recent_summary="\n".join(f"{m.role}: {m.text[:300]}" for m in recent),
        recent_messages=recent,
        history_truncated=len(case.messages) > 6 or any(m.truncated for m in recent),
        task_context=fields,
        checklist_progress=ChecklistProgressMemory(
            completed_items=[t.title for t in case.tasks if t.status in {"done", "skipped"}][:20],
            pending_items=[t.title for t in case.tasks if t.status in {"todo", "in_progress"}][:20],
        ),
        warnings=["case_material_is_untrusted_user_context"],
    )
