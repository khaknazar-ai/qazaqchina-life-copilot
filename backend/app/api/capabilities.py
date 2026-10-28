from typing import Annotated

from fastapi import APIRouter, Depends

from backend.app.config import Settings, get_settings
from backend.app.domain.enums import LanguageCode, UserScenario
from backend.app.llm.factory import supported_providers
from backend.app.schemas.capabilities import CapabilitiesResponse

router = APIRouter(prefix="/api", tags=["capabilities"])


@router.get("/capabilities", response_model=CapabilitiesResponse)
def get_capabilities(
    settings: Annotated[Settings, Depends(get_settings)],
) -> CapabilitiesResponse:
    return CapabilitiesResponse(
        app_name="QminiGuide API",
        environment=settings.APP_ENV,
        default_llm_provider=(
            "ollama" if settings.OLLAMA_CHAT_ENABLED else
            "qwen" if settings.QWEN_CHAT_ENABLED else settings.LLM_DEFAULT_PROVIDER
        ),
        default_llm_model=(
            settings.OLLAMA_MODEL if settings.OLLAMA_CHAT_ENABLED else
            settings.QWEN_CHAT_MODEL if settings.QWEN_CHAT_ENABLED else settings.LLM_DEFAULT_MODEL
        ),
        external_llm_enabled=settings.LLM_ENABLE_EXTERNAL or settings.QWEN_CHAT_ENABLED,
        local_persistence_enabled=settings.ENABLE_LOCAL_PERSISTENCE,
        supported_languages=[
            LanguageCode.ru.value,
            LanguageCode.kk.value,
            LanguageCode.zh.value,
            LanguageCode.en.value,
        ],
        supported_scenarios=[scenario.value for scenario in UserScenario],
        supported_llm_providers=[*supported_providers(), "qwen", "ollama"],
        feature_flags={
            "local_device_signin": settings.LOCAL_DEVICE_SIGNIN_ENABLED,
            "local_account_preview": settings.LOCAL_DEVICE_SIGNIN_ENABLED,
            "account_types": True,
            "consul_workspace": True,
            "local_ollama_chat": settings.OLLAMA_CHAT_ENABLED,
            "agent_workflow": any((
                settings.USE_AGENT_WORKFLOW, settings.OLLAMA_CHAT_ENABLED,
                settings.QWEN_CHAT_ENABLED, settings.CLOUD_RETRIEVAL_ENABLED,
            )),
            "cloud_chat": settings.QWEN_CHAT_ENABLED,
            "cloud_ocr": settings.QWEN_OCR_ENABLED,
            "cloud_retrieval": settings.CLOUD_RETRIEVAL_ENABLED,
            "cloud_reranking": settings.CLOUD_RETRIEVAL_ENABLED and settings.QWEN_RERANK_ENABLED,
            "semantic_conflict_review": settings.SEMANTIC_CONFLICT_REVIEW_ENABLED,
            "authenticated_source_publication": settings.ADMIN_AUTH_ENABLED
            and settings.ENABLE_LOCAL_PERSISTENCE,
            "cloud_document_explanation": settings.QWEN_CHAT_ENABLED,
            "saved_cases": True,
            "case_task_progress": True,
            "workspace_owner_isolation": True,
            "support_reply_flow": True,
            "support_staffed": False,
            "verified_emergency_contacts": False,
            "pilot_access_required": bool(settings.PILOT_ACCESS_TOKENS.get_secret_value())
            or any((settings.QWEN_CHAT_ENABLED, settings.QWEN_OCR_ENABLED,
                    settings.CLOUD_RETRIEVAL_ENABLED, settings.SEMANTIC_CONFLICT_REVIEW_ENABLED)),
            "source_governance": True,
            "community_moderation": True,
            "verified_contributors": True,
            "admin_review": True,
            "human_escalation": True,
            "multilingual": True,
            "checklist_engine": True,
            "local_persistence": settings.ENABLE_LOCAL_PERSISTENCE,
            "reporting": True,
            "llm_provider_adapter": True,
        },
    )
