import hashlib
from contextlib import nullcontext
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError

from backend.app.api.dependencies import (
    get_cloud_client,
    get_session_memory_service,
    get_source_registry,
    get_trace_service,
)
from backend.app.api_utils.pilot_access import bind_citizen_request
from backend.app.cloud_ai.chat import CloudChatService
from backend.app.cloud_ai.client import QwenCloudClient
from backend.app.config import Settings, get_settings
from backend.app.memory.service import SessionMemoryService
from backend.app.schemas.chat import ChatRequest, ChatResponse
from backend.app.services.chat_service import ChatService
from backend.app.services.trace_service import TraceService
from backend.app.source_registry.registry import SourceRegistry
from backend.app.workspace.api import get_workspace_owner, get_workspace_service
from backend.app.workspace.chat_context import (
    build_case_context,
    build_profile_context,
    case_session,
)
from backend.app.workspace.chat_turns import AttachTurnRequest, ServerTurnStore
from backend.app.workspace.message_city import message_city
from backend.app.workspace.service import clean_text

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    http_request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    trace_service: Annotated[TraceService, Depends(get_trace_service)],
    memory_service: Annotated[SessionMemoryService, Depends(get_session_memory_service)],
    source_registry: Annotated[SourceRegistry, Depends(get_source_registry)],
    cloud_client: Annotated[QwenCloudClient | None, Depends(get_cloud_client)],
) -> ChatResponse:
    client_session_id = request.session_id
    request = bind_citizen_request(http_request, request)
    owner = None
    if (
        request.case_id
        or getattr(http_request.state, "pilot_principal", None) is not None
        or http_request.headers.get("x-workspace-session")
    ):
        owner = get_workspace_owner(http_request)
    workspace = get_workspace_service(http_request) if owner else None
    if owner:
        clean_text(request.user_message)  # Reject image/key material before any provider call.
        session_key = owner + "\0" + (request.session_id or "current")
        if request.use_saved_context is False:
            session_key += "\0without-saved-context"
        request.session_id = "workspace-" + hashlib.sha256(session_key.encode()).hexdigest()
    transaction = (
        workspace.chat_transaction(owner, request.case_id) if request.case_id else nullcontext()
    )
    with transaction as case:
        case_context = None
        profile_context = None
        if case is None and not request.city:
            request.city = message_city(request.user_message)
        if case is not None:
            request.session_id = case_session(owner, case.case_id)
            if request.use_saved_context is False:
                request.session_id += "-without-context"
            else:
                request.city = case.context.city
            try:
                request.consistent_city()
            except (ValueError, ValidationError):
                raise HTTPException(
                    422,
                    "Source applicability city disagrees with the saved case city",
                ) from None
            if request.use_saved_context is not False:
                case_context = build_case_context(owner, case, request)
        elif workspace and request.use_saved_context is True:
            profile_context = build_profile_context(workspace.get_profile(owner), request)
            request.city = profile_context.city
            try:
                request.consistent_city()
            except (ValueError, ValidationError):
                raise HTTPException(
                    422, "Source applicability city disagrees with profile city",
                ) from None
        retrieval = None
        if settings.CLOUD_RETRIEVAL_ENABLED:
            from backend.app.cloud_ai.retrieval_runtime import build_cloud_retrieval

            retrieval = build_cloud_retrieval(settings, source_registry)
        # Every runtime reloads the publication ledger after retrieval/provider
        # work, before the answer is remembered or returned.
        registry_snapshot = (
            (lambda: source_registry)
            if get_source_registry in http_request.app.dependency_overrides
            else (lambda: get_source_registry(settings, http_request))
        )
        answer_service = None
        if settings.OLLAMA_CHAT_ENABLED:
            from backend.app.llm.ollama import OllamaChatService

            answer_service = OllamaChatService(
                http_request.app.state.ollama_client, registry_snapshot=registry_snapshot,
            )
        elif cloud_client and settings.QWEN_CHAT_ENABLED:
            answer_service = CloudChatService(cloud_client, registry_snapshot=registry_snapshot)
        response = ChatService(
            settings=settings,
            trace_service=trace_service,
            use_agent_workflow=any(
                (
                    settings.USE_AGENT_WORKFLOW,
                    settings.OLLAMA_CHAT_ENABLED,
                    settings.QWEN_CHAT_ENABLED,
                    settings.CLOUD_RETRIEVAL_ENABLED,
                )
            ),
            semantic_retrieval_service=retrieval,
            cloud_chat_service=answer_service,
            memory_service=memory_service,
            source_registry=source_registry,
            registry_snapshot=registry_snapshot,
            case_followup_context=case_context,
            profile_followup_context=profile_context,
            source_conflict_service=getattr(
                http_request.app.state,
                "source_conflict_service",
                None,
            ),
        ).create_response(request)
        response.session_id = client_session_id
        response.case_id = request.case_id
        if getattr(http_request.app.state, "source_review_mode", None) == "local_mvp_simulation":
            response.metadata.update(
                source_review_mode="local_mvp_simulation", independent_human_review=False,
                expert_review=False,
            )
        if owner:
            _turn_store(http_request).remember(
                owner, request.user_message, response, city=request.city,
            )
        if request.case_id:
            workspace.append_exchange(owner, request.case_id, request.user_message, response)
        return response


def _turn_store(request: Request) -> ServerTurnStore:
    # Created during app configuration before requests, with a lazy path for bare test apps.
    store = getattr(request.app.state, "chat_turn_store", None)
    if store is None:
        store = ServerTurnStore()
        request.app.state.chat_turn_store = store
    return store


@router.post("/workspace/cases/{case_id}/chat-turns")
def attach_chat_turn(case_id: str, body: AttachTurnRequest, request: Request) -> dict:
    owner = get_workspace_owner(request)
    service = get_workspace_service(request)
    case = service.get_case(owner, case_id)
    if any(message.trace_id == body.trace_id for message in case.messages):
        return {"case": case}
    turn = _turn_store(request).get(owner, body.trace_id)
    with service.chat_transaction(owner, case_id):
        return {"case": service.append_exchange(
            owner, case_id, turn.message, turn.response, city=turn.city,
        )}


@router.get("/access/check")
def check_pilot_access(request: Request) -> dict:
    return {"authenticated": getattr(request.state, "pilot_principal", None) is not None}
