from typing import Annotated

from fastapi import APIRouter, Depends, Request

from backend.app.api.dependencies import get_cloud_client, get_trace_service
from backend.app.cloud_ai.client import QwenCloudClient
from backend.app.config import Settings, get_settings
from backend.app.schemas.translate import TranslateExplainRequest, TranslateExplainResponse
from backend.app.services.trace_service import TraceService
from backend.app.services.translation_service import TranslationService

router = APIRouter(prefix="/api", tags=["translate"])


@router.post("/translate/explain", response_model=TranslateExplainResponse)
def explain_translation(
    request: TranslateExplainRequest,
    http_request: Request,
    trace_service: Annotated[TraceService, Depends(get_trace_service)],
    cloud_client: Annotated[QwenCloudClient | None, Depends(get_cloud_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TranslateExplainResponse:
    return TranslationService(
        trace_service=trace_service,
        cloud_client=cloud_client if settings.QWEN_CHAT_ENABLED else None,
        local_client=(
            http_request.app.state.ollama_client if settings.OLLAMA_CHAT_ENABLED else None
        ),
    ).explain(request)
