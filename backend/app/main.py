from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.app.admin_auth.service import build_admin_auth_service, validate_runtime_settings
from backend.app.api.admin import router as admin_router
from backend.app.api.admin_console import router as admin_console_router
from backend.app.api.capabilities import router as capabilities_router
from backend.app.api.cases import router as cases_router
from backend.app.api.chat import router as chat_router
from backend.app.api.checklists import router as checklists_router
from backend.app.api.community import router as community_router
from backend.app.api.demo import router as demo_router
from backend.app.api.emergency import router as emergency_router
from backend.app.api.evaluation_review import router as evaluation_review_router
from backend.app.api.health import router as health_router
from backend.app.api.human_support import router as human_support_router
from backend.app.api.photo_intake import router as photo_intake_router
from backend.app.api.privacy import router as privacy_router
from backend.app.api.source_conflicts import router as source_conflicts_router
from backend.app.api.source_corpus import router as source_corpus_router
from backend.app.api.sources import router as sources_router
from backend.app.api.traces import router as traces_router
from backend.app.api.translate import router as translate_router
from backend.app.api_utils.identity_boundary import IdentityResolver
from backend.app.api_utils.local_device_signin import LocalDeviceSignin
from backend.app.api_utils.local_device_signin import router as local_signin_router
from backend.app.api_utils.pilot_access import PilotAccessService
from backend.app.api_utils.request_guard import RequestGuard
from backend.app.cloud_ai.client import QwenCloudClient, validate_cloud_settings
from backend.app.config import Settings, get_settings
from backend.app.durable_storage.sqlite_store import SQLiteDurableStore
from backend.app.human_support.service import HumanSupportService
from backend.app.memory.service import SessionMemoryService
from backend.app.persistence.factory import build_admin_review_service, build_local_record_store
from backend.app.privacy.service import PrivacyService
from backend.app.source_conflicts import ConflictResolutionService
from backend.app.source_corpus.runtime import build_source_corpus_service
from backend.app.workspace.api import router as workspace_router
from backend.app.workspace.chat_turns import ServerTurnStore


def _configure_runtime(application: FastAPI, settings: Settings) -> None:
    validate_runtime_settings(settings)
    from backend.app.llm.ollama import OllamaClient, validate_ollama_settings

    validate_ollama_settings(settings)
    validate_cloud_settings(settings)
    pilot_access = PilotAccessService(settings)
    if getattr(application.state, "runtime_initialized", False):
        return
    application.state.runtime_settings = settings
    application.state.ollama_client = (
        OllamaClient(settings) if settings.OLLAMA_CHAT_ENABLED else None
    )
    application.state.pilot_access_service = pilot_access
    application.state.identity_resolver = IdentityResolver(
        pilot_access, preview_enabled=settings.LOCAL_DEVICE_SIGNIN_ENABLED,
    )
    application.state.local_device_signin = (
        LocalDeviceSignin(settings, pilot_access) if settings.LOCAL_DEVICE_SIGNIN_ENABLED else None
    )
    application.dependency_overrides[get_settings] = lambda: settings
    base_dir = Path(settings.LOCAL_DATA_DIR) if settings.ENABLE_LOCAL_PERSISTENCE else None
    store = SQLiteDurableStore(base_dir / "runtime.sqlite3") if base_dir else None
    application.state.durable_store = store
    application.state.admin_auth_service = build_admin_auth_service(settings)
    application.state.source_corpus_service = build_source_corpus_service(
        settings, admin_auth_service=application.state.admin_auth_service,
    )
    if settings.CLOUD_RETRIEVAL_ENABLED:
        from backend.app.embeddings.cloud_http import singapore_base_url

        singapore_base_url(settings.DASHSCOPE_BASE_URL)
    if settings.SEMANTIC_CONFLICT_REVIEW_ENABLED:
        from backend.app.source_conflicts.semantic_review import SemanticConflictReviewer

        application.state.cloud_client = QwenCloudClient(settings)
        application.state.semantic_conflict_reviewer = SemanticConflictReviewer(
            application.state.cloud_client,
        )
    application.state.admin_review_service = build_admin_review_service(base_dir)
    application.state.source_conflict_service = ConflictResolutionService(
        base_dir / "source_conflicts.sqlite3" if base_dir else ":memory:"
    )
    application.state.human_support_service = HumanSupportService(durable_store=store)
    application.state.privacy_service = PrivacyService(durable_store=store)
    application.state.chat_turn_store = ServerTurnStore()
    application.state.session_memory_service = SessionMemoryService(
        repository=(
            build_local_record_store(base_dir, "session_memory.jsonl") if base_dir else None
        )
    )
    application.state.runtime_initialized = True


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        _configure_runtime(application, settings or get_settings())
        yield

    application = FastAPI(
        title="QminiGuide API",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.add_middleware(RequestGuard)

    @application.exception_handler(RequestValidationError)
    async def safe_validation_error(_request, exc):
        # Pydantic's default includes rejected input (possibly a full photo or secret).
        return JSONResponse(status_code=422, content={"detail": [
            {"loc": list(error["loc"]), "type": error["type"], "msg": error["msg"]}
            for error in exc.errors()
        ]})
    if settings is not None:
        _configure_runtime(application, settings)
    for router in (
        health_router,
        capabilities_router,
        local_signin_router,
        chat_router,
        checklists_router,
        translate_router,
        emergency_router,
        photo_intake_router,
        human_support_router,
        privacy_router,
        community_router,
        cases_router,
        sources_router,
        source_conflicts_router,
        source_corpus_router,
        evaluation_review_router,
        traces_router,
        admin_router,
        admin_console_router,
        demo_router,
        workspace_router,
    ):
        application.include_router(router)
    return application


app = create_app()
